var lazy_callback = function() {
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
};

if (document.readyState === "complete" ||
    (document.readyState !== "loading" && !document.documentElement.doScroll)) {
    lazy_callback();
} else {
    document.addEventListener("DOMContentLoaded", callback);
}
