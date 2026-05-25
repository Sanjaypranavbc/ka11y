async () => {
    document.querySelectorAll('[data-src],[data-lazy-src],[data-original],[loading="lazy"]').forEach(el => {
        ['lazyload', 'lazyloaded', 'lazy-load'].forEach(evt => el.dispatchEvent(new Event(evt, { bubbles: true })));
        if (el.dataset.src) el.src = el.dataset.src;
        if (el.dataset.lazySrc) el.src = el.dataset.lazySrc;
        if (el.dataset.original) el.src = el.dataset.original;
    });

    const totalHeight = document.documentElement.scrollHeight;
    const steps = 6;
    for (let i = 1; i <= steps; i++) {
        window.scrollTo(0, (totalHeight / steps) * i);
        await new Promise(resolve => setTimeout(resolve, 200));
    }
    window.scrollTo(0, 0);
}
