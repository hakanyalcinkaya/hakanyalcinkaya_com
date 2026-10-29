// Video.js 10 oynatıcı paketi: Türkçe arayüz, varsayılan video görünümü; Bunny Stream için HLS, Vimeo için Vimeo kaynağı.
// HLS hls.js ile oynatılır: Bunny parçaları MPEG-TS veriyor, Video.js'in yerleşik HLS motoru (SPF) bunu oynatamıyor.
// Derleme: `npm run build` → static_files/js/videojs/player.js (Django bu dosyayı sunar).
import '@videojs/html/i18n';
import '@videojs/html/i18n/locales/tr/register';
import '@videojs/html/video/player';
import '@videojs/html/video/skin';
import '@videojs/html/media/hlsjs-video';
import '@videojs/html/media/vimeo-video';

export { preferQuality } from './quality.js';
export { enableVimeoQuality } from './vimeo-quality.js';
