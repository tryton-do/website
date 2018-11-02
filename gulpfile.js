var gulp = require('gulp');
var uglify = require('gulp-uglify');
var concat = require('gulp-concat');
var sass = require('gulp-sass');
var cleanCSS = require('gulp-clean-css');
var rename = require("gulp-rename");
var sourcemaps = require('gulp-sourcemaps');
var cssFileName = 'screen';

gulp.task('js', function() {
    gulp.src([
        'node_modules/jquery/dist/jquery.slim.js',
        'node_modules/popper.js/dist/umd/popper.js',
        'node_modules/bootstrap/dist/js/bootstrap.js',
        'node_modules/wowjs/dist/wow.js',
        'node_modules/leaflet/dist/leaflet.js',
        'js/wow.js',
        'js/highlight.pack.js',
        'js/highlight.js',
        'js/map.js'])
        .pipe(sourcemaps.init())
        .pipe(gulp.dest('static/js/'))
        .pipe(concat('all.js'))
        .pipe(uglify())
        .pipe(sourcemaps.write('.'))
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
