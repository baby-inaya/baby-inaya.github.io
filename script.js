// Global variables
let mediaItems = [];
let currentIndex = 0;

// DOM elements
const gallery = document.getElementById('gallery');
const thumbnailsContainer = document.getElementById('thumbnails');
const modal = document.getElementById('fullscreen-modal');
const modalImage = document.getElementById('modal-image');
const modalVideo = document.getElementById('modal-video');
const closeModal = document.getElementById('close-modal');
const prevBtn = document.getElementById('prev-btn');
const nextBtn = document.getElementById('next-btn');
const modalFilename = document.getElementById('modal-filename');
const modalCounter = document.getElementById('modal-counter');
const loading = document.getElementById('loading');

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    loadMediaItems();
});

// Load all media items from images and videos folders
async function loadMediaItems() {
    try {
        // In a real implementation, you would fetch the file list from the server
        // For now, we'll simulate this with the files we know exist
        const imageFiles = await getImageFiles();
        const videoFiles = await getVideoFiles();
        
        // Combine and sort by filename (chronological order)
        mediaItems = [...imageFiles, ...videoFiles].sort((a, b) => {
            return a.filename.localeCompare(b.filename);
        });
        
        if (mediaItems.length === 0) {
            showNoContentMessage();
        } else {
            renderGallery();
            renderThumbnails();
        }
        
        hideLoading();
    } catch (error) {
        console.error('Error loading media items:', error);
        showErrorMessage();
        hideLoading();
    }
}

// Get image files from the images folder
async function getImageFiles() {
    // In a real implementation, this would be a server request
    // For now, we'll return the files we know exist
    return [
        {
            type: 'image',
            src: 'images/Screenshot (212).png',
            filename: 'Screenshot (212).png',
            thumbnail: 'images/Screenshot (212).png'
        }
    ];
}

// Get video files from the videos folder
async function getVideoFiles() {
    // In a real implementation, this would be a server request
    // For now, we'll return the files we know exist
    return [
        {
            type: 'video',
            src: 'videos/2025-08-07 22-56-06.mp4',
            filename: '2025-08-07 22-56-06.mp4',
            thumbnail: 'videos/2025-08-07 22-56-06.mp4'
        }
    ];
}

// Render the main gallery
function renderGallery() {
    gallery.innerHTML = '';
    
    mediaItems.forEach((item, index) => {
        const galleryItem = createGalleryItem(item, index);
        gallery.appendChild(galleryItem);
    });
}

// Create a gallery item element
function createGalleryItem(item, index) {
    const div = document.createElement('div');
    div.className = 'gallery-item fade-in';
    div.dataset.index = index;
    
    if (item.type === 'image') {
        div.innerHTML = `
            <img src="${item.src}" alt="${item.filename}" loading="lazy">
        `;
    } else {
        div.innerHTML = `
            <video src="${item.src}" preload="metadata"></video>
            <div class="play-icon">▶</div>
        `;
    }
    
    div.addEventListener('click', () => openModal(index));
    return div;
}

// Render thumbnail navigation
function renderThumbnails() {
    thumbnailsContainer.innerHTML = '';
    
    mediaItems.forEach((item, index) => {
        const thumbnail = createThumbnail(item, index);
        thumbnailsContainer.appendChild(thumbnail);
    });
}

// Create a thumbnail element
function createThumbnail(item, index) {
    const div = document.createElement('div');
    div.className = 'thumbnail';
    div.dataset.index = index;
    
    if (item.type === 'image') {
        div.innerHTML = `<img src="${item.thumbnail}" alt="${item.filename}">`;
    } else {
        div.innerHTML = `
            <video src="${item.thumbnail}" preload="metadata"></video>
            <div class="play-icon" style="width: 20px; height: 20px; font-size: 0.8rem;">▶</div>
        `;
    }
    
    div.addEventListener('click', () => openModal(index));
    return div;
}

// Open full-screen modal
function openModal(index) {
    currentIndex = index;
    const item = mediaItems[index];
    
    // Hide all media elements
    modalImage.style.display = 'none';
    modalVideo.style.display = 'none';
    
    if (item.type === 'image') {
        modalImage.src = item.src;
        modalImage.alt = item.filename;
        modalImage.style.display = 'block';
    } else {
        modalVideo.src = item.src;
        modalVideo.style.display = 'block';
    }
    
    // Update modal info
    modalFilename.textContent = item.filename;
    modalCounter.textContent = `${index + 1} / ${mediaItems.length}`;
    
    // Update thumbnail active state
    updateThumbnailActiveState();
    
    // Show modal
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
    
    // Add scale-in animation
    modal.classList.add('scale-in');
}

// Close full-screen modal
function closeModalHandler() {
    modal.classList.remove('active');
    document.body.style.overflow = '';
    
    // Pause video if playing
    if (modalVideo.style.display !== 'none') {
        modalVideo.pause();
    }
}

// Navigate to previous item
function navigatePrev() {
    if (currentIndex > 0) {
        openModal(currentIndex - 1);
    } else {
        openModal(mediaItems.length - 1); // Loop to last item
    }
}

// Navigate to next item
function navigateNext() {
    if (currentIndex < mediaItems.length - 1) {
        openModal(currentIndex + 1);
    } else {
        openModal(0); // Loop to first item
    }
}

// Update thumbnail active state
function updateThumbnailActiveState() {
    const thumbnails = document.querySelectorAll('.thumbnail');
    thumbnails.forEach((thumb, index) => {
        if (index === currentIndex) {
            thumb.classList.add('active');
        } else {
            thumb.classList.remove('active');
        }
    });
}

// Hide loading spinner
function hideLoading() {
    loading.classList.add('hidden');
    setTimeout(() => {
        loading.style.display = 'none';
    }, 500);
}

// Show no content message
function showNoContentMessage() {
    gallery.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 3rem;">
            <h2 style="color: #831843; margin-bottom: 1rem;">No photos or videos yet</h2>
            <p style="color: #be185d;">Add some precious moments to the images/ and videos/ folders!</p>
        </div>
    `;
}

// Show error message
function showErrorMessage() {
    gallery.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 3rem;">
            <h2 style="color: #831843; margin-bottom: 1rem;">Oops! Something went wrong</h2>
            <p style="color: #be185d;">Please check your internet connection and try again.</p>
        </div>
    `;
}

// Event listeners
closeModal.addEventListener('click', closeModalHandler);
prevBtn.addEventListener('click', navigatePrev);
nextBtn.addEventListener('click', navigateNext);

// Keyboard navigation
document.addEventListener('keydown', function(e) {
    if (!modal.classList.contains('active')) return;
    
    switch(e.key) {
        case 'Escape':
            closeModalHandler();
            break;
        case 'ArrowLeft':
            navigatePrev();
            break;
        case 'ArrowRight':
            navigateNext();
            break;
    }
});

// Click outside modal to close
modal.addEventListener('click', function(e) {
    if (e.target === modal) {
        closeModalHandler();
    }
});

// Touch/swipe support for mobile
let touchStartX = 0;
let touchEndX = 0;

modal.addEventListener('touchstart', function(e) {
    touchStartX = e.changedTouches[0].screenX;
});

modal.addEventListener('touchend', function(e) {
    touchEndX = e.changedTouches[0].screenX;
    handleSwipe();
});

function handleSwipe() {
    const swipeThreshold = 50;
    const diff = touchStartX - touchEndX;
    
    if (Math.abs(diff) > swipeThreshold) {
        if (diff > 0) {
            navigateNext(); // Swipe left
        } else {
            navigatePrev(); // Swipe right
        }
    }
}

// Lazy loading for images
function lazyLoadImages() {
    const images = document.querySelectorAll('img[loading="lazy"]');
    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src || img.src;
                observer.unobserve(img);
            }
        });
    });
    
    images.forEach(img => imageObserver.observe(img));
}

// Initialize lazy loading
document.addEventListener('DOMContentLoaded', lazyLoadImages); 