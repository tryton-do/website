var gulp = require('gulp');
var uglify = require('gulp-uglify');
var concat = require('gulp-concat');
var sass = require('gulp-sass');
var autoprefixer = require('gulp-autoprefixer');
var cleanCSS = require('gulp-clean-css');
var rename = require("gulp-rename");
var sourcemaps = require('gulp-sourcemaps');
var iconfont = require('gulp-iconfont');
var iconfontCss = require('gulp-iconfont-css');
var sequence = require('run-sequence');
var cssFileName = 'screen';
var fontName = 'Icons';

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
        .pipe(autoprefixer())
        .pipe(cleanCSS())
        .pipe(sourcemaps.write('.'))
        .pipe(gulp.dest('static/css/'));
});

gulp.task('iconfont', function(callback) {
    gulp.src(['iconfont/*.svg'])
        .pipe(iconfontCss({
            fontName: fontName,
            targetPath: '../../sass/iconfont/_icons.scss',
            fontPath: '../../static/fonts/'
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

gulp.task('css', function(done) {
    sequence('iconfont', 'sass', done);
});

gulp.task('watch', function() {
    gulp.watch(['sass/*', 'sass/*/*', 'sass/*/*/*'], ['sass']);
    gulp.watch(['iconfont/*'], ['iconfont']);
});

gulp.task('default', ['js', 'css']);
