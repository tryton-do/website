var gulp = require('gulp');
var uglify = require('gulp-uglify');
var concat = require('gulp-concat');
var sass = require('gulp-sass');
var sassPackageImporter = require('node-sass-package-importer');
var autoprefixer = require('gulp-autoprefixer');
var cleanCSS = require('gulp-clean-css');
var sourcemaps = require('gulp-sourcemaps');
var iconfont = require('gulp-iconfont');
var iconfontCss = require('gulp-iconfont-css');
var touch = require('gulp-touch-fd');
var fontName = 'Icons';

gulp.task('main-js', function() {
    return gulp.src([
        'node_modules/jquery/dist/jquery.slim.js',
        'node_modules/popper.js/dist/umd/popper.js',
        'node_modules/bootstrap/dist/js/bootstrap.js',
        'node_modules/loading-attribute-polyfill/dist/loading-attribute-polyfill.umd.js',
        'js/highlight.pack.js',
        'js/highlight.js',
        'js/lazy.js'])
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
        }).on('error', sass.logError))
        .pipe(autoprefixer())
        .pipe(cleanCSS())
        .pipe(sourcemaps.write('.'))
        .pipe(gulp.dest('static/css/'))
        .pipe(touch());
});

gulp.task('iconfont', function(callback) {
    gulp.src(['iconfont/*.svg'])
        .pipe(iconfontCss({
            fontName: fontName,
            targetPath: '../../sass/iconfont/_icons.scss',
            fontPath: '/static/fonts/'
        }))
        .pipe(iconfont({
            fontName: fontName,
            formats: ['svg', 'ttf', 'eot', 'woff', 'woff2'],
            normalize: true,
            fontHeight: 1000
        }))
        .pipe(gulp.dest('static/fonts/'))
        .on('end', callback);
});

gulp.task('css', gulp.series(['iconfont', 'sass']));
gulp.task('js', gulp.parallel(['main-js', 'map-js']));

gulp.task('watch', function() {
    gulp.watch(['sass/**/*.scss'], gulp.parallel(['sass']));
    gulp.watch(['iconfont/*'], gulp.parallel(['iconfont']));
});

gulp.task('default', gulp.parallel(['js', 'css']));
