document.addEventListener("DOMContentLoaded", function() {
    const lazyImages = [].slice.call(document.querySelectorAll("img.lazy-load"));

    if ("IntersectionObserver" in window) {
        let lazyImageObserver = new IntersectionObserver(function(entries, observer) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    let lazyImage = entry.target;
                    if (lazyImage.dataset.src) {
                        lazyImage.src = lazyImage.dataset.src;
                        lazyImage.removeAttribute('data-src'); // Clean up
                    }
                    // Optional: if using data-srcset for responsive images
                    // if (lazyImage.dataset.srcset) {
                    //     lazyImage.srcset = lazyImage.dataset.srcset;
                    //     lazyImage.removeAttribute('data-srcset');
                    // }
                    lazyImage.classList.remove("lazy-load");
                    lazyImage.classList.add("lazy-loaded");
                    observer.unobserve(lazyImage); // Stop observing the image once loaded
                }
            });
        }, {
            rootMargin: "0px 0px 50px 0px" // Start loading images when they are 50px from entering the viewport
        });

        lazyImages.forEach(function(lazyImage) {
            lazyImageObserver.observe(lazyImage);
        });
    } else {
        // Fallback for older browsers that don't support IntersectionObserver
        // Load all images immediately
        lazyImages.forEach(function(lazyImage) {
            if (lazyImage.dataset.src) {
                lazyImage.src = lazyImage.dataset.src;
                lazyImage.removeAttribute('data-src');
            }
            // if (lazyImage.dataset.srcset) {
            //     lazyImage.srcset = lazyImage.dataset.srcset;
            //     lazyImage.removeAttribute('data-srcset');
            // }
            lazyImage.classList.remove("lazy-load");
            lazyImage.classList.add("lazy-loaded");
        });
    }
});