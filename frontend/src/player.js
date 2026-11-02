// Video.js 10 oynatıcı paketi: Türkçe arayüz, varsayılan video görünümü; Bunny Stream için HLS, Vimeo için Vimeo kaynağı.
// HLS hls.js ile oynatılır: Bunny parçaları MPEG-TS veriyor, Video.js'in yerleşik HLS motoru (SPF) bunu oynatamıyor.
// Derleme: `npm run build` → static_files/js/videojs/player.js (Django bu dosyayı sunar).
import '@videojs/html/i18n';
import '@videojs/html/i18n/locales/tr/register';
import '@videojs/html/video/player';
import '@videojs/html/video/skin';
import '@videojs/html/media/hlsjs-video';
import '@videojs/html/media/vimeo-video';

// Oynatmaya basılınca kapak görseli Video.js'teki sürenin (0,25 sn) yarısında kaybolur. Görünüm shadow DOM içinde
// olduğu için kural sitenin CSS'inden değil, görünümün kendi stil sayfasının sonuna eklenerek verilir; "hareketi
// azalt" tercihinde Video.js'in anında geçişi korunur.
const POSTER_FADE = '@media (prefers-reduced-motion: no-preference) { .media-skin .media-poster { transition-duration: .125s; } }';
const VideoSkin = customElements.get('video-skin');
if (typeof VideoSkin.styles === 'string') {
  VideoSkin.styles += POSTER_FADE;
} else {
  VideoSkin.styles.insertRule(POSTER_FADE, VideoSkin.styles.cssRules.length);
}

export { preferQuality } from './quality.js';
export { enableVimeoQuality } from './vimeo-quality.js';
