// Video.js 10 oynatıcı paketi: Türkçe arayüz, varsayılan video görünümü ve HLS kaynağı (Bunny Stream).
// HLS hls.js ile oynatılır: Bunny parçaları MPEG-TS veriyor, Video.js'in yerleşik HLS motoru (SPF) bunu oynatamıyor.
// Derleme: `npm run build` → static_files/js/videojs/player.js (Django bu dosyayı sunar).
import '@videojs/html/i18n';
import '@videojs/html/i18n/locales/tr/register';
import '@videojs/html/video/player';
import '@videojs/html/video/skin';
import '@videojs/html/media/hlsjs-video';

export { preferQuality } from './quality.js';
