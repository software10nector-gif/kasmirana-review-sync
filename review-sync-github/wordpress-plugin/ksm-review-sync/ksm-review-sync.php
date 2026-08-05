<?php
/**
 * Plugin Name: Kasmirana Marketplace Review Sync
 * Description: Receives Flipkart/Meesho reviews pushed by the free GitHub
 *              Actions scraper and displays them on the WooCommerce product page.
 * Version: 1.0.0
 * Author: Kasmirana
 *
 * SECURITY NOTE: This plugin never talks to Flipkart/Meesho itself and never
 * scrapes anything. It only exposes a REST endpoint that accepts data pushed
 * by the trusted GitHub Actions workflow, authenticated by an Application
 * Password PLUS a shared secret defined in wp-config.php:
 *
 *     define( 'KSM_REVIEW_SYNC_SECRET', 'a-long-random-string' );
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

define( 'KSM_REVIEW_SYNC_VERSION', '1.0.0' );
define( 'KSM_REVIEW_SYNC_DIR', plugin_dir_path( __FILE__ ) );
define( 'KSM_REVIEW_SYNC_URL', plugin_dir_url( __FILE__ ) );

require_once KSM_REVIEW_SYNC_DIR . 'includes/class-ksm-review-db.php';
require_once KSM_REVIEW_SYNC_DIR . 'includes/class-ksm-review-rest-api.php';
require_once KSM_REVIEW_SYNC_DIR . 'includes/class-ksm-review-display.php';

register_activation_hook( __FILE__, [ 'KSM_Review_DB', 'install' ] );

add_action( 'plugins_loaded', function () {
    KSM_Review_REST_API::init();
    KSM_Review_Display::init();
} );
