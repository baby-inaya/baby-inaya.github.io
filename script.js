/* The generated manifest is the only list to maintain when new memories arrive. */
(() => {
    'use strict';

    const PAGE_SIZE = 24;
    const FAVORITES_KEY = 'inaya:favorites:v1';
    const MONTH_FORMAT = new Intl.DateTimeFormat('en', { month: 'long', year: 'numeric' });
    const DATE_FORMAT = new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: 'numeric' });
    const ICONS = {
        heart: ['M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z'],
        play: ['m9 5 11 7-11 7V5Z'],
        photo: ['M4 3h16a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z', 'm3 16 6-6 5 5 3-3 4 4', 'M16 7h.01']
    };
    const $ = (id) => document.getElementById(id);
    const element = (tag, className, text) => {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    };
    const icon = (name) => {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('fill', name === 'play' ? 'currentColor' : 'none');
        svg.setAttribute('stroke', 'currentColor');
        svg.setAttribute('stroke-width', '1.6');
        svg.setAttribute('stroke-linecap', 'round');
        svg.setAttribute('stroke-linejoin', 'round');
        svg.setAttribute('aria-hidden', 'true');
        svg.setAttribute('focusable', 'false');
        ICONS[name].forEach((d) => {
            const path = document.createElementNS(svg.namespaceURI, 'path');
            path.setAttribute('d', d);
            svg.append(path);
        });
        return svg;
    };
    // Manifest paths are raw relative filenames, including literal spaces, # and %.
    const mediaUrl = (path) => String(path).replace(/\\/g, '/').split('/').map(encodeURIComponent).join('/');
    const fileName = (item) => item.src.replace(/\\/g, '/').split('/').pop();
    const parsedDate = (date) => {
        if (typeof date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
        const parsed = new Date(`${date}T12:00:00`);
        const [year, month, day] = date.split('-').map(Number);
        return parsed.getFullYear() === year && parsed.getMonth() + 1 === month && parsed.getDate() === day ? parsed : null;
    };
    const dateLabel = (item) => item.date ? DATE_FORMAT.format(parsedDate(item.date)) : 'A memory to keep';
    const durationLabel = (seconds) => {
        if (!Number.isFinite(seconds) || seconds <= 0) return '';
        const total = Math.round(seconds);
        const hours = Math.floor(total / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const remainder = String(total % 60).padStart(2, '0');
        return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${remainder}` : `${minutes}:${remainder}`;
    };

    function start() {
        const gallery = $('gallery');
        if (!gallery) return;
        const library = window.MEDIA_LIBRARY;
        const seenIds = new Set();
        const items = (Array.isArray(library?.items) ? library.items : [])
            .filter((item) => item && typeof item.src === 'string' && ['image', 'video'].includes(item.type))
            .map((item) => ({ ...item, id: String(item.id || item.src), title: String(item.title || fileName(item)), album: String(item.album || 'Everyday moments'), date: parsedDate(item.date) ? item.date : null }))
            .filter((item) => {
                if (seenIds.has(item.id)) return false;
                seenIds.add(item.id);
                return true;
            });
        const byId = new Map(items.map((item) => [item.id, item]));
        const albums = [...new Set(items.map((item) => item.album))].sort((a, b) => a.localeCompare(b));
        const years = [...new Set(items.filter((item) => item.date).map((item) => item.date.slice(0, 4)))].sort().reverse();
        let favorites = readFavorites();
        let filters = { type: 'all', query: '', album: '', year: '', sort: 'newest' };
        let filteredItems = [];
        let visibleCount = PAGE_SIZE;
        let modalItems = [];
        let modalIndex = -1;
        let opener = null;
        let previousOverflow = '';
        let searchTimer;
        const dialog = $('memory-dialog');
        const modalImage = $('modal-image');
        const modalVideo = $('modal-video');

        function readFavorites() {
            try {
                const stored = JSON.parse(localStorage.getItem(FAVORITES_KEY) || '[]');
                return new Set(Array.isArray(stored) ? stored.filter((id) => typeof id === 'string' && byId.has(id)) : []);
            } catch { return new Set(); }
        }

        function updateCounts() {
            const counts = { all: items.length, image: items.filter((item) => item.type === 'image').length, video: items.filter((item) => item.type === 'video').length, favorites: favorites.size };
            document.querySelectorAll('[data-count]').forEach((node) => {
                if (Object.hasOwn(counts, node.dataset.count)) node.textContent = counts[node.dataset.count].toLocaleString();
            });
            const stats = { 'stat-total': counts.all, 'stat-photos': counts.image, 'stat-videos': counts.video, 'stat-chapters': albums.length };
            Object.entries(stats).forEach(([id, count]) => { if ($(id)) $(id).textContent = count.toLocaleString(); });
        }

        function updateFavoriteButton(button, item) {
            const saved = favorites.has(item.id);
            button.classList.toggle('is-favorite', saved);
            button.setAttribute('aria-pressed', String(saved));
            button.setAttribute('aria-label', `${saved ? 'Remove' : 'Save'} ${item.title} ${saved ? 'from' : 'to'} Little favorites`);
            button.title = saved ? 'Remove from Little favorites' : 'Save to Little favorites';
        }

        function toggleFavorite(item) {
            if (favorites.has(item.id)) favorites.delete(item.id);
            else favorites.add(item.id);
            try { localStorage.setItem(FAVORITES_KEY, JSON.stringify([...favorites])); }
            catch { /* Favorites still work for this visit when storage is unavailable. */ }
            const focusWasInGallery = gallery.contains(document.activeElement);
            if (filters.type === 'favorites') {
                applyFilters();
                if (focusWasInGallery) (gallery.querySelector('.favorite-toggle') || document.querySelector('[data-filter="favorites"]'))?.focus({ preventScroll: true });
            } else {
                gallery.querySelectorAll('[data-favorite-id]').forEach((button) => {
                    const favoriteItem = byId.get(button.dataset.favoriteId);
                    if (favoriteItem) updateFavoriteButton(button, favoriteItem);
                });
            }
            if (modalItems[modalIndex] && $('modal-favorite')) updateFavoriteButton($('modal-favorite'), modalItems[modalIndex]);
            updateCounts();
        }

        function makeThumbnail(item, className = '') {
            const wrapper = element('span', className);
            const fallback = element('span', 'thumbnail-fallback');
            fallback.append(icon(item.type === 'video' ? 'play' : 'photo'));
            fallback.setAttribute('aria-hidden', 'true');
            wrapper.append(fallback);
            const source = item.thumbnail || (item.type === 'image' ? item.src : '');
            if (source) {
                const img = element('img');
                img.alt = '';
                img.loading = 'lazy';
                img.decoding = 'async';
                img.src = mediaUrl(source);
                fallback.hidden = true;
                img.addEventListener('error', () => { img.hidden = true; fallback.hidden = false; }, { once: true });
                wrapper.append(img);
            }
            return wrapper;
        }

        function makeCard(item) {
            const card = element('article', 'memory-card');
            const open = element('button', 'memory-open');
            open.type = 'button';
            open.setAttribute('aria-label', `Open ${item.type === 'video' ? 'video' : 'photo'}: ${item.title}, ${dateLabel(item)}`);
            const visual = makeThumbnail(item, 'memory-visual');
            visual.classList.add(item.type === 'video' ? 'is-video' : 'is-photo');
            visual.append(element('span', 'memory-kind', item.type === 'video' ? 'Film' : 'Photo'));
            if (item.type === 'video') {
                const play = element('span', 'play-badge');
                play.setAttribute('aria-hidden', 'true');
                play.append(icon('play'));
                visual.append(play);
                const duration = durationLabel(item.duration);
                if (duration) visual.append(element('span', 'duration-badge', duration));
            }
            const caption = element('span', 'memory-caption');
            caption.append(element('span', 'memory-title', item.title));
            const date = element('time', 'memory-date', dateLabel(item));
            if (item.date) date.dateTime = item.date;
            caption.append(date);
            open.append(visual, caption);
            open.addEventListener('click', () => openMemory(item, filteredItems, open));
            const favorite = element('button', 'favorite-toggle');
            favorite.type = 'button';
            favorite.dataset.favoriteId = item.id;
            favorite.append(icon('heart'));
            updateFavoriteButton(favorite, item);
            favorite.addEventListener('click', () => toggleFavorite(item));
            card.append(open, favorite);
            return card;
        }

        function renderGallery() {
            const fragment = document.createDocumentFragment();
            let lastMonth = null;
            let grid;
            const monthCounts = new Map();
            filteredItems.forEach((item) => {
                const month = item.date?.slice(0, 7) || 'undated';
                monthCounts.set(month, (monthCounts.get(month) || 0) + 1);
            });
            filteredItems.slice(0, visibleCount).forEach((item) => {
                const month = item.date?.slice(0, 7) || 'undated';
                if (month !== lastMonth) {
                    const section = element('section', 'month-group');
                    const heading = element('div', 'month-heading');
                    const title = element('h3', '', item.date ? MONTH_FORMAT.format(parsedDate(item.date)) : 'Timeless little moments');
                    const count = monthCounts.get(month);
                    heading.append(title, element('span', 'month-count', `${count} ${count === 1 ? 'memory' : 'memories'}`));
                    grid = element('div', 'memory-grid');
                    section.append(heading, grid);
                    fragment.append(section);
                    lastMonth = month;
                }
                grid.append(makeCard(item));
            });
            gallery.replaceChildren(fragment);
            const shown = Math.min(visibleCount, filteredItems.length);
            if ($('results-count')) $('results-count').textContent = filteredItems.length ? `${shown} of ${filteredItems.length.toLocaleString()} ${filteredItems.length === 1 ? 'memory' : 'memories'}` : 'No memories found';
            if ($('empty-state')) $('empty-state').hidden = filteredItems.length !== 0;
            if ($('load-more')) {
                $('load-more').hidden = shown >= filteredItems.length;
                $('load-more').textContent = `More little moments (${Math.min(PAGE_SIZE, filteredItems.length - shown)})`;
            }
            const hasFilters = filters.type !== 'all' || filters.query || filters.album || filters.year || filters.sort !== 'newest';
            if ($('clear-filters')) $('clear-filters').hidden = !hasFilters;
        }

        function applyFilters({ resetPage = false, history = null } = {}) {
            if (resetPage) visibleCount = PAGE_SIZE;
            const terms = filters.query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
            filteredItems = items.filter((item) => {
                if (filters.type === 'favorites' ? !favorites.has(item.id) : filters.type !== 'all' && item.type !== filters.type) return false;
                if (filters.album && item.album !== filters.album) return false;
                if (filters.year && item.date?.slice(0, 4) !== filters.year) return false;
                const searchable = `${item.title} ${item.album} ${fileName(item)} ${item.date || ''} ${item.date ? `${DATE_FORMAT.format(parsedDate(item.date))} ${MONTH_FORMAT.format(parsedDate(item.date))}` : 'undated'}`.toLocaleLowerCase();
                return terms.every((term) => searchable.includes(term));
            }).sort((a, b) => {
                if (!a.date && b.date) return 1;
                if (a.date && !b.date) return -1;
                const dateOrder = (a.date || '').localeCompare(b.date || '');
                return (filters.sort === 'oldest' ? dateOrder : -dateOrder) || a.src.localeCompare(b.src);
            });
            syncControls();
            renderGallery();
            if (history) writeUrl(history);
        }

        function syncControls() {
            if ($('search-input')) $('search-input').value = filters.query;
            if ($('album-filter')) $('album-filter').value = filters.album;
            if ($('year-filter')) $('year-filter').value = filters.year;
            if ($('sort-order')) $('sort-order').value = filters.sort;
            document.querySelectorAll('#filter-buttons [data-filter]').forEach((button) => {
                const active = button.dataset.filter === filters.type;
                button.classList.toggle('is-active', active);
                button.setAttribute('aria-pressed', String(active));
            });
        }

        function readUrl() {
            const params = new URL(window.location.href).searchParams;
            const type = params.get('type');
            filters = { type: ['image', 'video', 'favorites'].includes(type) ? type : 'all', query: params.get('q') || '', album: albums.includes(params.get('album')) ? params.get('album') : '', year: years.includes(params.get('year')) ? params.get('year') : '', sort: params.get('sort') === 'oldest' ? 'oldest' : 'newest' };
        }

        function writeUrl(mode) {
            const url = new URL(window.location.href);
            const values = { q: filters.query, type: filters.type === 'all' ? '' : filters.type, album: filters.album, year: filters.year, sort: filters.sort === 'newest' ? '' : filters.sort };
            Object.entries(values).forEach(([key, value]) => value ? url.searchParams.set(key, value) : url.searchParams.delete(key));
            if (url.href === window.location.href) return;
            try { window.history[mode === 'push' ? 'pushState' : 'replaceState'](null, '', url); }
            catch { /* Local file previews may disallow history updates. */ }
        }

        function clearVideo() {
            if (!modalVideo) return;
            modalVideo.pause();
            modalVideo.removeAttribute('src');
            modalVideo.removeAttribute('poster');
            modalVideo.load();
        }

        function showModalItem() {
            const item = modalItems[modalIndex];
            if (!item || !dialog) return;
            clearVideo();
            if (modalImage) { modalImage.hidden = true; modalImage.removeAttribute('src'); }
            if (modalVideo) modalVideo.hidden = true;
            if ($('modal-error')) $('modal-error').hidden = true;
            const url = mediaUrl(item.src);
            if (item.type === 'image' && modalImage) {
                modalImage.alt = item.title;
                modalImage.src = url;
                modalImage.hidden = false;
            } else if (modalVideo) {
                modalVideo.preload = 'metadata';
                modalVideo.playsInline = true;
                modalVideo.controls = true;
                if (item.thumbnail) modalVideo.poster = mediaUrl(item.thumbnail);
                modalVideo.src = mediaUrl(item.playbackSrc || item.src);
                modalVideo.hidden = false;
            }
            if ($('modal-title')) $('modal-title').textContent = item.title;
            if ($('modal-meta')) $('modal-meta').textContent = [dateLabel(item), item.album, item.type === 'video' ? durationLabel(item.duration) : 'Photo'].filter(Boolean).join(' · ');
            if ($('modal-position')) $('modal-position').textContent = `${modalIndex + 1} / ${modalItems.length}`;
            if ($('modal-download')) { $('modal-download').href = url; $('modal-download').download = fileName(item); }
            if ($('modal-favorite')) updateFavoriteButton($('modal-favorite'), item);
            ['modal-prev', 'modal-next'].forEach((id) => { if ($(id)) $(id).disabled = modalItems.length < 2; });
        }

        function openMemory(item, sequence, source) {
            if (!dialog) return;
            const wasOpen = dialog.open;
            modalItems = sequence.length ? [...sequence] : [item];
            modalIndex = modalItems.findIndex((entry) => entry.id === item.id);
            if (modalIndex < 0) { modalItems = [item]; modalIndex = 0; }
            if (!wasOpen) {
                opener = source || document.activeElement;
                previousOverflow = document.body.style.overflow;
                document.body.style.overflow = 'hidden';
            }
            showModalItem();
            if (!wasOpen) {
                if (typeof dialog.showModal === 'function') dialog.showModal();
                else dialog.setAttribute('open', '');
                $('modal-close')?.focus({ preventScroll: true });
            }
        }

        function cleanupModal() {
            clearVideo();
            modalImage?.removeAttribute('src');
            document.body.style.overflow = previousOverflow;
            modalIndex = -1;
            modalItems = [];
            const returnFocus = opener?.isConnected ? opener : document.querySelector('#filter-buttons [aria-pressed="true"]');
            returnFocus?.focus({ preventScroll: true });
            opener = null;
        }
        function closeModal() {
            if (!dialog?.open) return;
            if (typeof dialog.close === 'function') dialog.close();
            else { dialog.removeAttribute('open'); cleanupModal(); }
        }
        function navigateModal(direction) {
            if (modalItems.length < 2) return;
            modalIndex = (modalIndex + direction + modalItems.length) % modalItems.length;
            showModalItem();
        }

        function setupModal() {
            if (!dialog) return;
            $('modal-close')?.addEventListener('click', closeModal);
            $('modal-prev')?.addEventListener('click', () => navigateModal(-1));
            $('modal-next')?.addEventListener('click', () => navigateModal(1));
            $('modal-favorite')?.addEventListener('click', () => { if (modalItems[modalIndex]) toggleFavorite(modalItems[modalIndex]); });
            dialog.addEventListener('close', cleanupModal);
            dialog.addEventListener('click', (event) => {
                if (event.target !== dialog) return;
                const bounds = dialog.getBoundingClientRect();
                if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) closeModal();
            });
            dialog.addEventListener('keydown', (event) => {
                if (event.target.closest('video, input, textarea, select') || event.altKey || event.ctrlKey || event.metaKey) return;
                if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); navigateModal(event.key === 'ArrowLeft' ? -1 : 1); }
                else if (event.key === 'Escape' && typeof dialog.close !== 'function') closeModal();
            });
            const showError = (kind) => {
                const item = modalItems[modalIndex];
                if (!item || item.type !== kind || !$('modal-error')) return;
                $('modal-error').textContent = `This ${kind === 'video' ? 'video' : 'photo'} cannot be displayed in this browser. Use the download button to save this memory.`;
                $('modal-error').hidden = false;
            };
            modalImage?.addEventListener('error', () => showError('image'));
            modalVideo?.addEventListener('error', () => showError('video'));
            // Photo swipes leave video seeking and player controls untouched.
            let touchStart = null;
            modalImage?.addEventListener('touchstart', (event) => {
                touchStart = event.touches.length === 1 ? { x: event.touches[0].clientX, y: event.touches[0].clientY, at: Date.now() } : null;
            }, { passive: true });
            modalImage?.addEventListener('touchend', (event) => {
                if (!touchStart || !event.changedTouches.length) return;
                const dx = event.changedTouches[0].clientX - touchStart.x;
                const dy = event.changedTouches[0].clientY - touchStart.y;
                if (Date.now() - touchStart.at < 700 && Math.abs(dx) > 65 && Math.abs(dx) > Math.abs(dy) * 1.5) navigateModal(dx < 0 ? 1 : -1);
                touchStart = null;
            }, { passive: true });
            modalImage?.addEventListener('touchcancel', () => { touchStart = null; }, { passive: true });
        }

        function setupHighlights() {
            const ordered = [...items].sort((a, b) => (b.date || '').localeCompare(a.date || '') || a.src.localeCompare(b.src));
            const hero = items.find((item) => item.src === 'images/Screenshot (212).png')
                || ordered.find((item) => item.type === 'image' && item.thumbnail)
                || ordered.find((item) => item.type === 'image')
                || ordered.find((item) => item.thumbnail);
            if (hero) {
                if ($('hero-image')) {
                    $('hero-image').src = mediaUrl(hero.thumbnail || hero.src);
                    $('hero-image').alt = hero.src === 'images/Screenshot (212).png'
                        ? 'A treasured family memory with Inaya' : hero.title;
                    $('hero-image').addEventListener('error', () => { $('hero-image').hidden = true; }, { once: true });
                }
                if ($('hero-caption')) $('hero-caption').textContent = 'A little moment, a forever memory';
                $('hero-memory')?.addEventListener('click', () => openMemory(hero, ordered, $('hero-memory')));
            } else if ($('hero-memory')) $('hero-memory').hidden = true;
            const featured = items.find((item) => item.src === 'videos/VID_20251021_191323.mp4')
                || items.find((item) => item.src === 'videos/2025-08-07 22-56-06.mp4')
                || ordered.find((item) => item.type === 'video' && item.thumbnail && item.duration > 0 && item.duration <= 60 && !/nvidia|desktop/i.test(item.src))
                || ordered.find((item) => item.type === 'video' && item.thumbnail)
                || ordered.find((item) => item.type === 'video');
            if (featured) {
                if ($('featured-video')) $('featured-video').hidden = false;
                if ($('featured-video-image') && featured.thumbnail) {
                    $('featured-video-image').src = mediaUrl(featured.thumbnail);
                    $('featured-video-image').alt = featured.title;
                    $('featured-video-image').addEventListener('error', () => { $('featured-video-image').hidden = true; }, { once: true });
                }
                if ($('featured-video-duration')) $('featured-video-duration').textContent = durationLabel(featured.duration) || 'Play a little moment';
                $('featured-video')?.setAttribute('aria-label', `Watch ${featured.title}`);
                $('featured-video')?.addEventListener('click', () => openMemory(featured, ordered.filter((item) => item.type === 'video'), $('featured-video')));
            } else if ($('featured-video')) $('featured-video').hidden = true;
            if ($('age-label')) {
                const birth = new Date(2025, 3, 22);
                const now = new Date();
                let months = (now.getFullYear() - birth.getFullYear()) * 12 + now.getMonth() - birth.getMonth();
                if (now.getDate() < birth.getDate()) months--;
                months = Math.max(0, months);
                const ageYears = Math.floor(months / 12);
                const ageMonths = months % 12;
                $('age-label').textContent = months === 0 ? 'A beautiful beginning' : [ageYears ? `${ageYears} ${ageYears === 1 ? 'year' : 'years'}` : '', ageMonths ? `${ageMonths} ${ageMonths === 1 ? 'month' : 'months'}` : ''].filter(Boolean).join(', ') + ' of wonder';
            }
            if ($('album-shortcuts')) {
                const counts = albums.map((album) => ({ album, entries: ordered.filter((item) => item.album === album) }))
                    .sort((a, b) => Number(/nvidia|desktop|screen.?record/i.test(a.album)) - Number(/nvidia|desktop|screen.?record/i.test(b.album)) || b.entries.length - a.entries.length || a.album.localeCompare(b.album));
                const fragment = document.createDocumentFragment();
                counts.slice(0, 4).forEach(({ album, entries }) => {
                    const button = element('button', 'album-card');
                    button.type = 'button';
                    button.append(makeThumbnail(entries.find((item) => item.thumbnail) || entries[0], 'album-card-image'));
                    const copy = element('span', 'album-card-copy');
                    copy.append(element('span', 'album-card-title', album), element('span', 'album-card-count', `${entries.length} ${entries.length === 1 ? 'memory' : 'memories'}`));
                    button.append(copy);
                    button.addEventListener('click', () => {
                        clearTimeout(searchTimer);
                        filters = { type: 'all', query: '', album, year: '', sort: 'newest' };
                        applyFilters({ resetPage: true, history: 'push' });
                        ($('memories') || gallery).scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' });
                        $('album-filter')?.focus({ preventScroll: true });
                    });
                    fragment.append(button);
                });
                $('album-shortcuts').replaceChildren(fragment);
            }
        }

        function setupControls() {
            [['album-filter', albums], ['year-filter', years]].forEach(([id, values]) => {
                if (!$(id)) return;
                if ($(id).options.length) $(id).options[0].value = '';
                values.forEach((value) => { const option = element('option', '', value); option.value = value; $(id).append(option); });
            });
            $('search-input')?.addEventListener('input', () => {
                filters.query = $('search-input').value;
                clearTimeout(searchTimer);
                searchTimer = setTimeout(() => applyFilters({ resetPage: true, history: 'replace' }), 180);
            });
            [['album-filter', 'album'], ['year-filter', 'year'], ['sort-order', 'sort']].forEach(([id, key]) => {
                $(id)?.addEventListener('change', () => { clearTimeout(searchTimer); filters[key] = $(id).value; applyFilters({ resetPage: true, history: 'push' }); });
            });
            document.querySelectorAll('#filter-buttons [data-filter]').forEach((button) => {
                button.addEventListener('click', () => { clearTimeout(searchTimer); filters.type = button.dataset.filter; applyFilters({ resetPage: true, history: 'push' }); });
            });
            $('clear-filters')?.addEventListener('click', () => {
                clearTimeout(searchTimer);
                filters = { type: 'all', query: '', album: '', year: '', sort: 'newest' };
                applyFilters({ resetPage: true, history: 'push' });
                $('search-input')?.focus({ preventScroll: true });
            });
            $('load-more')?.addEventListener('click', () => {
                const previousCount = Math.min(visibleCount, filteredItems.length);
                visibleCount += PAGE_SIZE;
                renderGallery();
                gallery.querySelectorAll('.memory-open')[previousCount]?.focus({ preventScroll: true });
            });
            window.addEventListener('popstate', () => { clearTimeout(searchTimer); readUrl(); applyFilters({ resetPage: true }); });
            window.addEventListener('storage', (event) => {
                if (event.key !== FAVORITES_KEY && event.key !== null) return;
                favorites = readFavorites();
                applyFilters();
                updateCounts();
                if (modalItems[modalIndex] && $('modal-favorite')) updateFavoriteButton($('modal-favorite'), modalItems[modalIndex]);
            });
        }

        setupControls();
        setupModal();
        setupHighlights();
        readUrl();
        updateCounts();
        applyFilters();
        if (!items.length && $('empty-state')) {
            const heading = $('empty-state').querySelector('h2, h3');
            const copy = $('empty-state').querySelector('p');
            if (heading) heading.textContent = library ? 'The story is just beginning' : 'The memory library could not load';
            if (copy) copy.textContent = library ? 'New photos and little films will appear here as the collection grows.' : 'Please refresh the page to try loading the collection again.';
        }
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
    else start();
})();
