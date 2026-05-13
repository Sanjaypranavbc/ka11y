() => {
    function queryShadow(root, selector) {
        const results = [];
        const queue = [root];
        const seen = new Set();
        while (queue.length) {
            const current = queue.shift();
            if (!current || !current.querySelectorAll) continue;
            current.querySelectorAll(selector).forEach(el => {
                if (!seen.has(el)) {
                    seen.add(el);
                    results.push(el);
                }
            });
            current.querySelectorAll('*').forEach(el => {
                if (el.shadowRoot) queue.push(el.shadowRoot);
            });
        }
        return results;
    }

    return queryShadow(document, 'a[href]')
        .map(a => a.href || a.getAttribute('href'))
        .filter(Boolean);
}
