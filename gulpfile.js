var gulp = require('gulp');
var concat = require('gulp-concat');
var sass = require('gulp-sass');
var cleanCSS = require('gulp-clean-css');
var rename = require("gulp-rename");
var sourcemaps = require('gulp-sourcemaps');
var cssFileName = 'screen';

gulp.task('js', function() {
    gulp.src([
        'node_modules/jquery/dist/jquery.slim.min.js',
        'node_modules/popper.js/dist/umd/popper.min.js',
        'node_modules/bootstrap/dist/js/bootstrap.min.js',
        'node_modules/wowjs/dist/wow.min.js',
        'node_modules/leaflet/dist/leaflet.js',
        'js/wow.js',
        'js/highlight.pack.js',
        'js/highlight.js',
        'js/map.js'])
        .pipe(concat('all.js'))
        .pipe(gulp.dest('static/js/'));
});

gulp.task('sass', function() {
    gulp.src('sass/' + cssFileName + '.scss')
        .pipe(sourcemaps.init())
        .pipe(sass({outputStyle: 'compressed'}).on('error', sass.logError))
        .pipe(rename(cssFileName + '.min.css'))
        .pipe(cleanCSS())
        .pipe(sourcemaps.write('.'))
        .pipe(gulp.dest('static/css/'));
});

gulp.task('watch', function() {
    gulp.watch(['sass/*', 'sass/*/*', 'sass/*/*/*'], ['sass']);
});

gulp.task('default', ['js', 'sass','watch']);
