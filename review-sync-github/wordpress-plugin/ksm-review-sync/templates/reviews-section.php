<?php
/** Variables available: $reviews (array), $stats (array) */
if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

$source_labels = [
    'flipkart' => 'Flipkart',
    'meesho'   => 'Meesho',
];
?>
<section class="ksm-mp-reviews" id="ksm-marketplace-reviews">
    <div class="ksm-mp-reviews__header">
        <span class="ksm-mp-reviews__eyebrow">Verified Buyers</span>
        <h2 class="ksm-mp-reviews__title">What Customers Are Saying</h2>

        <?php if ( ! empty( $stats ) ) : ?>
            <div class="ksm-mp-reviews__badges">
                <?php foreach ( $stats as $stat ) :
                    $label = $source_labels[ $stat['source_slug'] ] ?? ucfirst( $stat['source_slug'] );
                    ?>
                    <span class="ksm-mp-badge ksm-mp-badge--<?php echo esc_attr( $stat['source_slug'] ); ?>">
                        <strong><?php echo esc_html( number_format( (float) $stat['overall_rating'], 1 ) ); ?>★</strong>
                        on <?php echo esc_html( $label ); ?>
                        <span class="ksm-mp-badge__count">(<?php echo esc_html( number_format_i18n( (int) $stat['total_reviews'] ) ); ?> reviews)</span>
                    </span>
                <?php endforeach; ?>
            </div>
        <?php endif; ?>
    </div>

    <div class="ksm-mp-reviews__track">
        <?php foreach ( $reviews as $review ) :
            $source = $review['source_slug'];
            $label  = $source_labels[ $source ] ?? ucfirst( $source );
            ?>
            <article class="ksm-mp-card">
                <div class="ksm-mp-card__stars" aria-label="<?php echo esc_attr( $review['rating'] ); ?> out of 5 stars">
                    <?php for ( $i = 1; $i <= 5; $i++ ) : ?>
                        <span class="ksm-mp-star <?php echo $i <= (int) $review['rating'] ? 'is-filled' : ''; ?>">★</span>
                    <?php endfor; ?>
                </div>

                <?php if ( ! empty( $review['review_title'] ) ) : ?>
                    <h3 class="ksm-mp-card__title"><?php echo esc_html( $review['review_title'] ); ?></h3>
                <?php endif; ?>

                <p class="ksm-mp-card__text"><?php echo esc_html( wp_trim_words( $review['review_text'], 40 ) ); ?></p>

                <div class="ksm-mp-card__footer">
                    <span class="ksm-mp-card__name"><?php echo esc_html( $review['reviewer_name'] ); ?></span>
                    <span class="ksm-mp-card__source ksm-mp-card__source--<?php echo esc_attr( $source ); ?>">
                        via <?php echo esc_html( $label ); ?>
                    </span>
                </div>
            </article>
        <?php endforeach; ?>
    </div>
</section>
