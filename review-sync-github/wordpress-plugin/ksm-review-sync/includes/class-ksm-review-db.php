<?php
/**
 * Custom table storage for synced marketplace reviews. This is the ONLY
 * persistent database in the whole system — the GitHub Actions scraper has
 * no database of its own, so this table is the single source of truth.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

class KSM_Review_DB {

    public static function table_name() {
        global $wpdb;
        return $wpdb->prefix . 'ksm_marketplace_reviews';
    }

    public static function stats_table_name() {
        global $wpdb;
        return $wpdb->prefix . 'ksm_marketplace_stats';
    }

    public static function install() {
        global $wpdb;
        $charset_collate = $wpdb->get_charset_collate();

        $reviews_table = self::table_name();
        $stats_table   = self::stats_table_name();

        $sql = "CREATE TABLE {$reviews_table} (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            source_slug VARCHAR(32) NOT NULL,
            reviewer_name VARCHAR(255) NOT NULL DEFAULT 'Anonymous',
            rating TINYINT UNSIGNED NOT NULL,
            review_title VARCHAR(512) NULL,
            review_text TEXT NULL,
            review_date DATE NULL,
            external_fingerprint VARCHAR(128) NULL,
            is_visible TINYINT(1) NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY  (id),
            KEY source_slug (source_slug),
            KEY rating (rating),
            UNIQUE KEY uq_fingerprint (external_fingerprint)
        ) {$charset_collate};

        CREATE TABLE {$stats_table} (
            source_slug VARCHAR(32) NOT NULL,
            overall_rating DECIMAL(2,1) NOT NULL DEFAULT 0.0,
            total_reviews INT UNSIGNED NOT NULL DEFAULT 0,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY  (source_slug)
        ) {$charset_collate};";

        require_once ABSPATH . 'wp-admin/includes/upgrade.php';
        dbDelta( $sql );
    }

    /**
     * Insert a review pushed from the scraper. Returns the row id, or the
     * existing row id if this fingerprint was already synced — this is what
     * makes it safe for GitHub Actions to re-scrape and re-push everything
     * every 12 hours without ever creating duplicates.
     */
    public static function insert_review( array $review ) {
        global $wpdb;
        $table = self::table_name();

        $fingerprint = self::make_fingerprint( $review );

        $existing = $wpdb->get_var(
            $wpdb->prepare( "SELECT id FROM {$table} WHERE external_fingerprint = %s", $fingerprint )
        );
        if ( $existing ) {
            return (int) $existing;
        }

        $wpdb->insert(
            $table,
            [
                'source_slug'          => sanitize_key( $review['source_slug'] ),
                'reviewer_name'        => sanitize_text_field( $review['reviewer_name'] ),
                'rating'               => (int) $review['rating'],
                'review_title'         => isset( $review['review_title'] ) ? sanitize_text_field( $review['review_title'] ) : null,
                'review_text'          => isset( $review['review_text'] ) ? sanitize_textarea_field( $review['review_text'] ) : null,
                'review_date'          => ! empty( $review['review_date'] ) ? sanitize_text_field( $review['review_date'] ) : null,
                'external_fingerprint' => $fingerprint,
            ],
            [ '%s', '%s', '%d', '%s', '%s', '%s', '%s' ]
        );

        return (int) $wpdb->insert_id;
    }

    public static function upsert_stats( string $source_slug, float $overall_rating, int $total_reviews ) {
        global $wpdb;
        $table = self::stats_table_name();

        $wpdb->query(
            $wpdb->prepare(
                "INSERT INTO {$table} (source_slug, overall_rating, total_reviews)
                 VALUES (%s, %f, %d)
                 ON DUPLICATE KEY UPDATE overall_rating = VALUES(overall_rating), total_reviews = VALUES(total_reviews)",
                sanitize_key( $source_slug ),
                $overall_rating,
                $total_reviews
            )
        );
    }

    public static function get_visible_reviews( int $limit = 20 ) {
        global $wpdb;
        $table = self::table_name();

        return $wpdb->get_results(
            $wpdb->prepare(
                "SELECT source_slug, reviewer_name, rating, review_title, review_text, review_date
                 FROM {$table}
                 WHERE is_visible = 1
                 ORDER BY review_date DESC, id DESC
                 LIMIT %d",
                $limit
            ),
            ARRAY_A
        );
    }

    public static function get_all_stats() {
        global $wpdb;
        $table = self::stats_table_name();
        return $wpdb->get_results( "SELECT * FROM {$table}", ARRAY_A );
    }

    private static function make_fingerprint( array $review ) : string {
        $basis = strtolower( trim(
            ( $review['source_slug'] ?? '' ) . '|' .
            ( $review['reviewer_name'] ?? '' ) . '|' .
            ( $review['review_text'] ?? '' ) . '|' .
            ( $review['review_date'] ?? '' )
        ) );
        return hash( 'sha256', $basis );
    }
}
