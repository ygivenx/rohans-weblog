(() => {
    const content = document.querySelector('article .content');
    if (!content) return;

    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const el = (tag, cls, text) => {
        const node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text) node.textContent = text;
        return node;
    };

    /* ---- Ticker tape: upgrade the "Ticker (...):" paragraph ---- */
    const buildTicker = () => {
        const para = [...content.querySelectorAll(':scope > p')].find((p) => {
            const lead = p.firstElementChild;
            return lead?.tagName === 'STRONG' && /^Ticker\b/i.test(lead.textContent);
        });
        if (!para) return;

        const leadText = para.firstElementChild.textContent;
        const items = para.textContent
            .slice(leadText.length)
            .split('·')
            .map((s) => s.trim().replace(/\.$/, ''))
            .filter(Boolean);
        if (items.length < 3) return;

        const group = el('div', 'dg-ticker-group');
        for (let text of items) {
            const tick = el('span', 'dg-tick');
            const m = text.match(/\s*\(?([+\-−]\s?\d[\d.,]*%)\)?$/);
            const chg = m ? m[1] : null;
            if (m) text = text.slice(0, m.index).trim();

            const sp = text.indexOf(' ');
            const name = sp === -1 ? text : text.slice(0, sp);
            const value = sp === -1 ? '' : text.slice(sp + 1);

            if (name) tick.append(el('span', 'dg-tick-name', name));
            if (value) tick.append(el('span', 'dg-tick-value', value));
            if (chg) {
                tick.append(
                    el('span', `dg-tick-chg ${chg[0] === '+' ? 'dg-up' : 'dg-down'}`, chg)
                );
            }
            group.append(tick);
        }

        const clone = group.cloneNode(true);
        clone.setAttribute('aria-hidden', 'true');

        const track = el('div', 'dg-ticker-track');
        track.append(group, clone);

        const viewport = el('div', 'dg-ticker-viewport');
        viewport.append(track);

        const wrap = el('div', 'dg-ticker');
        wrap.append(el('div', 'dg-ticker-label', leadText.replace(/:\s*$/, '')), viewport);
        para.replaceWith(wrap);

        const width = group.getBoundingClientRect().width;
        if (width > 0) {
            track.style.setProperty('--dg-ticker-duration', `${Math.max(12, Math.round(width / 55))}s`);
        }
    };

    /* ---- Reading progress bar (CSS scroll-driven when supported, rAF fallback) ---- */
    const buildProgress = () => {
        if (reduce) return;
        const bar = el('div', 'dg-progress');
        bar.setAttribute('aria-hidden', 'true');
        document.body.append(bar);

        if (CSS.supports?.('animation-timeline: scroll()')) return;

        let queued = false;
        const paint = () => {
            queued = false;
            const max = document.documentElement.scrollHeight - innerHeight;
            const p = max > 0 ? Math.min(1, Math.max(0, scrollY / max)) : 0;
            bar.style.transform = `scaleX(${p})`;
        };
        const onScroll = () => {
            if (!queued) {
                queued = true;
                requestAnimationFrame(paint);
            }
        };
        addEventListener('scroll', onScroll, { passive: true });
        addEventListener('resize', onScroll, { passive: true });
        paint();
    };

    /* ---- Scroll reveal for elements below the fold (batched reads -> writes) ---- */
    const buildReveal = () => {
        if (reduce || !('IntersectionObserver' in window)) return;

        const cutoff = innerHeight * 0.92;
        const below = [...content.children].filter(
            (child) => child.getBoundingClientRect().top >= cutoff
        );
        if (!below.length) return;

        const io = new IntersectionObserver(
            (entries) => {
                for (const entry of entries) {
                    if (entry.isIntersecting || entry.boundingClientRect.top < 0) {
                        entry.target.classList.add('dg-in');
                        io.unobserve(entry.target);
                    }
                }
            },
            { rootMargin: '0px 0px -8% 0px', threshold: 0.01 }
        );

        for (const child of below) {
            child.classList.add('dg-reveal');
            io.observe(child);
        }
    };

    /* ---- Smooth open/close for <details> via single delegated listener ---- */
    const buildDetails = () => {
        if (reduce || !Element.prototype.animate) return;

        const anims = new WeakMap();
        content.addEventListener('click', (ev) => {
            const summary = ev.target.closest('summary');
            const details = summary?.parentElement;
            if (!details || details.tagName !== 'DETAILS' || !content.contains(details)) return;
            if (ev.target.closest('a')) return;

            ev.preventDefault();
            const prev = anims.get(details);
            const start = details.offsetHeight;
            const closing = details.open && !prev?.closing;

            prev?.anim.cancel();
            if (!closing) details.open = true;

            const end = closing ? summary.offsetHeight : details.offsetHeight;
            const anim = details.animate(
                { height: [`${start}px`, `${end}px`] },
                { duration: 320, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' }
            );
            const state = { anim, closing };
            anims.set(details, state);

            const cleanup = () => {
                if (anims.get(details) === state) anims.delete(details);
            };
            anim.oncancel = cleanup;
            anim.onfinish = () => {
                if (closing) details.open = false;
                cleanup();
            };
        });
    };

    buildTicker();
    buildProgress();
    buildReveal();
    buildDetails();
})();
