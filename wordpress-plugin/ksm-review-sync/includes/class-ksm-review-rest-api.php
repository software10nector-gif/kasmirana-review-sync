<?php
/**
 * REST endpoints used by the GitHub Actions scraper.
 *
 * Auth (two independent factors, both required):
 *   1. WordPress Application Password (standard Basic Auth) — proves the
 *      caller has valid WP admin credentials.
 *   2. X-KSM-Sync-Secret header — a long random string, defined only in
 *      wp-config.php (never in the database), matching the
 *      WP_SYNC_SHARED_SECRET GitHub Secret. Even a leaked Application
 *      Password alone can't hit this endpoint without it.
 *
 * Rate limiting: capped via a transient counter so a compromised or buggy
 * workflow run can't flood the reviews table.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

class KSM_Review_REST_API {

    const NAMESPACE_ = 'ksm-reviews/v1';
    const RATE_LIMIT_PER_MINUTE = 60;

    public static function init() {
        add_action( 'rest_api_init', [ __CLASS__, 'register_routes' ] );
    }

    public static function register_routes() {
        register_rest_route( self::NAMESPACE_, '/sync', [
            'methods'             => 'POST',
            'callback'            => [ __CLASS__, 'handle_sync' ],
            'permission_callback' => [ __CLASS__, 'check_permissions' ],
            'args'                => [
                'source_slug'   => [ 'required' => true, 'type' => 'string' ],
                'reviewer_name' => [ 'required' => true, 'type' => 'string' ],
                'rating'        => [ 'required' => true, 'type' => 'integer' ],
                'review_title'  => [ 'required' => false, 'type' => 'string' ],
                'review_text'   => [ 'required' => false, 'type' => 'string' ],
                'review_date'   => [ 'required' => false, 'type' => 'string' ],
            ],
        ] );

        register_rest_route( self::NAMESPACE_, '/stats', [
            'methods'             => 'POST',
            'callback'            => [ __CLASS__, 'handle_stats' ],
            'permission_callback' => [ __CLASS__, 'check_permissions' ],
            'args'                => [
                'source_slug'    => [ 'required' => true, 'type' => 'string' ],
                'overall_rating' => [ 'required' => true, 'type' => 'number' ],
                'total_reviews'  => [ 'required' => true, 'type' => 'integer' ],
            ],
        ] );
    }

    public static function check_permissions( WP_REST_Request $request ) {
        if ( ! is_user_logged_in() || ! current_user_can( 'manage_options' ) ) {
            return new WP_Error( 'ksm_forbidden', 'Authentication required.', [ 'status' => 401 ] );
        }

        $provided_secret = $request->get_header( 'x-ksm-sync-secret' );
        if ( ! defined( 'KSM_REVIEW_SYNC_SECRET' ) || empty( $provided_secret )
             || ! hash_equals( KSM_REVIEW_SYNC_SECRET, $provided_secret ) ) {
            return new WP_Error( 'ksm_forbidden', 'Invalid sync secret.', [ 'status' => 401 ] );
        }

        if ( ! self::under_rate_limit() ) {
            return new WP_Error( 'ksm_rate_limited', 'Too many requests.', [ 'status' => 429 ] );
        }

        return true;
    }

    private static function under_rate_limit() : bool {
        $key   = 'ksm_review_sync_rate_' . gmdate( 'YmdHi' );
        $count = (int) get_transient( $key );
        if ( $count >= self::RATE_LIMIT_PER_MINUTE ) {
            return false;
        }
        set_transient( $key, $count + 1, 90 );
        return true;
    }

    public static function handle_sync( WP_REST_Request $request ) {
        $rating = (int) $request->get_param( 'rating' );
        if ( $rating < 1 || $rating > 5 ) {
            return new WP_Error( 'ksm_invalid_rating', 'Rating must be 1-5.', [ 'status' => 400 ] );
        }

        $source_slug = sanitize_key( $request->get_param( 'source_slug' ) );
        if ( ! in_array( $source_slug, [ 'flipkart', 'meesho' ], true ) ) {
            return new WP_Error( 'ksm_invalid_source', 'Unknown source_slug.', [ 'status' => 400 ] );
        }

        // Server-side safety net: only 4-5 star reviews are ever stored,
        // even if the scraper's own filtering is ever misconfigured.
        if ( $rating < 4 ) {
            return new WP_Error( 'ksm_below_threshold', 'Only 4-5 star reviews are accepted.', [ 'status' => 400 ] );
        }

        $review_id = KSM_Review_DB::insert_review( [
            'source_slug'   => $source_slug,
            'reviewer_name' => $request->get_param( 'reviewer_name' ),
            'rating'        => $rating,
            'review_title'  => $request->get_param( 'review_title' ),
            'review_text'   => $request->get_param( 'review_text' ),
            'review_date'   => $request->get_param( 'review_date' ),
        ] );

        do_action( 'litespeed_purge_all' );

        return rest_ensure_response( [ 'id' => $review_id ] );
    }

    public static function handle_stats( WP_REST_Request $request ) {
        $source_slug = sanitize_key( $request->get_param( 'source_slug' ) );
        if ( ! in_array( $source_slug, [ 'flipkart', 'meesho' ], true ) ) {
            return new WP_Error( 'ksm_invalid_source', 'Unknown source_slug.', [ 'status' => 400 ] );
        }

        KSM_Review_DB::upsert_stats(
            $source_slug,
            (float) $request->get_param( 'overall_rating' ),
            (int) $request->get_param( 'total_reviews' )
        );

        do_action( 'litespeed_purge_all' );

        return rest_ensure_response( [ 'ok' => true ] );
    }
}
