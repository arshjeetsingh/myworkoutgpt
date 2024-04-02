document.addEventListener("DOMContentLoaded", function() {
    var scrollToProBtn = document.querySelector('.btn-1');
    if (scrollToProBtn) {
        scrollToProBtn.addEventListener('click', function(e) {
            e.preventDefault();
            var targetSection = document.getElementById('proSection');
            smoothScrollTo(targetSection.offsetTop, 700); // Adjust 700(ms) to change the duration
        });
    }
});

function smoothScrollTo(targetPosition, duration) {
    var startPosition = window.pageYOffset;
    var distance = targetPosition - startPosition;
    var startTime = null;

    function animation(currentTime) {
        if (startTime === null) startTime = currentTime;
        var timeElapsed = currentTime - startTime;
        var run = ease(timeElapsed, startPosition, distance, duration);
        window.scrollTo(0, run);
        if (timeElapsed < duration) requestAnimationFrame(animation);
    }

    function ease(t, b, c, d) {
        t /= d / 2;
        if (t < 1) return c / 2 * t * t + b;
        t--;
        return -c / 2 * (t * (t - 2) - 1) + b;
    }

    requestAnimationFrame(animation);
}
