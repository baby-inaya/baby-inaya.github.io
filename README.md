# 👶 Inaya Mahnoor - Baby Portfolio

A beautiful, responsive static website to showcase precious photos and videos of baby Inaya Mahnoor. Built with pure HTML, CSS, and JavaScript for fast loading and easy maintenance.

## ✨ Features

- **🎨 Beautiful Pink Theme** - Perfect for a baby girl
- **📱 Fully Responsive** - Looks great on mobile, tablet, and desktop
- **🖼️ Dynamic Gallery** - Automatically displays all images and videos from folders
- **🎥 Full-Screen Modal** - Click any media to view in full screen
- **⬅️➡️ Navigation** - Arrow keys, swipe gestures, and thumbnail navigation
- **⚡ Fast Loading** - Optimized for performance with lazy loading
- **🎯 Touch-Friendly** - Swipe gestures for mobile users
- **♿ Accessible** - Keyboard navigation and screen reader support

## 📁 File Structure

```
baby-inaya.github.io/
├── index.html          # Main webpage
├── style.css           # All styling (pink theme)
├── script.js           # Interactive functionality
├── images/             # Place all baby photos here
│   └── Screenshot (212).png
├── videos/             # Place all baby videos here
│   └── 2025-08-07 22-56-06.mp4
└── README.md           # This file
```

## 🚀 How to Use

### Adding New Photos/Videos

1. **For Photos**: Simply drop any image file (JPG, PNG, GIF, etc.) into the `images/` folder
2. **For Videos**: Drop any video file (MP4, WebM, etc.) into the `videos/` folder
3. **File Naming**: Use descriptive names like `first-smile.jpg` or `crawling-milestone.mp4`
4. **Ordering**: Files will be displayed in alphabetical order by filename

### Website Features

- **Gallery View**: All media appears in a responsive grid
- **Thumbnail Navigation**: Scroll through thumbnails at the bottom
- **Full-Screen Mode**: Click any image/video to view in full screen
- **Navigation Controls**:
  - Left/Right arrow buttons
  - Keyboard arrow keys
  - Swipe gestures on mobile
  - Click thumbnails to jump to specific item

## 🎨 Customization

### Changing Colors
The website uses a pink theme. To change colors, edit these CSS variables in `style.css`:

```css
/* Main pink colors */
--primary-pink: #ec4899;
--dark-pink: #be185d;
--light-pink: #fdf2f8;
```

### Adding Baby Info
Update the header in `index.html`:

```html
<h1 class="baby-name">Inaya Mahnoor</h1>
<p class="baby-info">Born April 22, 2025</p>
```

## 📱 Mobile Experience

- **Touch Gestures**: Swipe left/right in full-screen mode
- **Responsive Design**: Automatically adapts to screen size
- **Fast Loading**: Optimized images and lazy loading
- **Easy Navigation**: Large touch targets and smooth animations

## 🔧 Technical Details

### Browser Support
- ✅ Chrome, Firefox, Safari, Edge
- ✅ Mobile browsers (iOS Safari, Chrome Mobile)
- ✅ Modern JavaScript features

### Performance Features
- **Lazy Loading**: Images load as you scroll
- **Optimized Media**: Responsive images and videos
- **Smooth Animations**: CSS transitions and transforms
- **Minimal JavaScript**: Lightweight and fast

### Accessibility
- **Keyboard Navigation**: Arrow keys and Escape
- **Screen Reader Support**: Proper alt text and ARIA labels
- **High Contrast**: Readable text and clear buttons
- **Focus Management**: Proper tab order and focus indicators

## 🚀 Deployment

### GitHub Pages
1. Push your code to a GitHub repository
2. Go to Settings > Pages
3. Select your main branch as source
4. Your site will be available at `https://yourusername.github.io/repository-name`

### Local Testing
1. Open `index.html` in any modern web browser
2. Or use a local server: `python -m http.server 8000`
3. Visit `http://localhost:8000`

## 📝 Maintenance

### Regular Updates
- Add new photos and videos to their respective folders
- The website will automatically detect and display new files
- No code changes needed for new content

### File Management
- **Recommended Image Formats**: JPG, PNG, WebP
- **Recommended Video Formats**: MP4, WebM
- **File Size**: Keep images under 5MB and videos under 50MB for fast loading
- **Naming**: Use descriptive names with dates if desired

## 🎯 Future Enhancements

Potential features you could add:
- **Date Captions**: Display dates for each photo/video
- **Categories**: Organize by milestones (first smile, first steps, etc.)
- **Music Background**: Optional background music
- **Share Buttons**: Easy sharing to social media
- **Print Mode**: Special layout for printing photos
- **Slideshow Mode**: Automatic slideshow with timer

## 💝 Special Features for Inaya

- **Personalized Header**: Shows Inaya's name and birth date
- **Pink Theme**: Perfect for a baby girl
- **Growth Tracking**: Easy to add photos as she grows
- **Family Sharing**: Simple URL to share with family and friends

---

**Made with ❤️ for Inaya Mahnoor**

*Born April 22, 2025* 