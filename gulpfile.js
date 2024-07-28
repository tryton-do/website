var gulp = require('gulp');
var uglify = require('gulp-uglify');
var concat = require('gulp-concat');
var sass = require('gulp-sass')(require('sass'));
var sassPackageImporter = require('node-sass-package-importer');
var autoprefixer = require('gulp-autoprefixer');
var cleanCSS = require('gulp-clean-css');
var sourcemaps = require('gulp-sourcemaps');
var touch = require('gulp-touch-fd');
var fontName = 'Icons';

gulp.task('main-js', function() {
    return gulp.src([
        'node_modules/@popperjs/core/dist/umd/popper.js',
        'node_modules/bootstrap/dist/js/bootstrap.js',
        'js/highlight.pack.js',
        'js/highlight.js',
    ])
        .pipe(sourcemaps.init())
        .pipe(gulp.dest('static/js/'))
        .pipe(concat('main.js'))
        .pipe(uglify())
        .pipe(sourcemaps.write('.'))
        .pipe(gulp.dest('static/js/'))
        .pipe(touch());
});

gulp.task('map-js', function() {
    return gulp.src([
        'node_modules/leaflet/dist/leaflet.js',
        'js/map.js'])
        .pipe(sourcemaps.init())
        .pipe(gulp.dest('static/js/'))
        .pipe(concat('map.js'))
        .pipe(uglify())
        .pipe(sourcemaps.write('.'))
        .pipe(gulp.dest('static/js/'))
        .pipe(touch());
});

gulp.task('sass', function() {
    return gulp.src('sass/**/*.scss')
        .pipe(sourcemaps.init())
        .pipe(sass({
            importer: sassPackageImporter(),
            outputStyle: 'compressed',
            quietDeps: true,
        }).on('error', sass.logError))
        .pipe(autoprefixer())
        .pipe(cleanCSS())
        .pipe(sourcemaps.write('.'))
        .pipe(gulp.dest('static/css/'))
        .pipe(touch());
});

gulp.task('css', gulp.series(['sass']));
gulp.task('js', gulp.parallel(['main-js', 'map-js']));

gulp.task('watch', function() {
    gulp.watch(['sass/**/*.scss'], gulp.parallel(['sass']));
});

gulp.task('default', gulp.parallel(['js', 'css']));
