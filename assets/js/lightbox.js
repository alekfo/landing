(function () {
    const overlay = document.getElementById('lightbox');
    const img     = document.getElementById('lightbox-img');
    const close   = document.getElementById('lightbox-close');

    document.querySelectorAll('.gallery-item img, .screenshots-grid img').forEach(function (el) {
        el.addEventListener('click', function () {
            img.src = el.src;
            img.alt = el.alt;
            overlay.classList.add('active');
            document.body.style.overflow = 'hidden';
        });
    });

    function closeLightbox() {
        overlay.classList.remove('active');
        document.body.style.overflow = '';
    }

    close.addEventListener('click', function (e) {
        e.stopPropagation();
        closeLightbox();
    });

    overlay.addEventListener('click', closeLightbox);

    img.addEventListener('click', function (e) {
        e.stopPropagation();
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeLightbox();
    });
})();