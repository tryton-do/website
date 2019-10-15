$(document).ready(function() {
    if ("IntersectionObserver" in window) {
        lazyElements = document.querySelectorAll(".lazy");
        var lazyObserver = new IntersectionObserver(function(entries, observer) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    var element = entry.target;
                    element.classList.remove("lazy");
                    lazyObserver.unobserve(element);
                }
            });
        });

        lazyElements.forEach(function(element) {
            lazyObserver.observe(element);
        });
    }
});
