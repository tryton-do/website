if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
        if (typeof setupMap !== 'undefined') {
            setupMap();
        }
    });
} else {
    if (typeof setupMap !== 'undefined') {
        setupMap();
    }
}
