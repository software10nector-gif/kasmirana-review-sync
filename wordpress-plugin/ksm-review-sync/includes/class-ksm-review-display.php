<?php
/**
 * Renders the synced marketplace reviews on the WooCommerce product page,
 * plus a [ksm_marketplace_reviews] shortcode for placing it anywhere else.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

class KSM_Review_Display {

    public static function init() {
        add_action( 'wp_enqueue_scripts', [ __CLASS__, 'enqueue_assets' ] );
        add_action( 'woocommerce_after_single_product_summary', [ __CLASS__, 'render_on_product_page' ], 12 );
        add_shortcode( 'ksm_marketplace_reviews', [ __CLASS__, 'render_shortcode' ] );
    }

    public static function enqueue_assets() {
        if ( ! is_product() && ! self::current_page_has_shortcode() ) {
            return;
        }
        wp_enqueue_style( 'ksm-review-sync', KSM_REVIEW_SYNC_URL . 'assets/css/reviews.css', [], KSM_REVIEW_SYNC_VERSION );
        wp_enqueue_script( 'ksm-review-sync', KSM_REVIEW_SYNC_URL . 'assets/js/reviews.js', [], KSM_REVIEW_SYNC_VERSION, true );
    }

    private static function current_page_has_shortcode() : bool {
        global $post;
        return $post && has_shortcode( $post->post_content ?? '', 'ksm_marketplace_reviews' );
    }

    public static function render_on_product_page() {
        echo self::render_shortcode( [] ); // phpcs:ignore WordPress.Security.EscapeOutput
    }

    public static function render_shortcode( $atts ) {
        $atts = shortcode_atts( [ 'limit' => 12 ], $atts );

        $reviews = KSM_Review_DB::get_visible_reviews( (int) $atts['limit'] );
        $stats   = KSM_Review_DB::get_all_stats();

        if ( empty( $reviews ) ) {
            return '';
        }

        ob_start();
        include KSM_REVIEW_SYNC_DIR . 'templates/reviews-section.php';
        return ob_get_clean();
    }
}
