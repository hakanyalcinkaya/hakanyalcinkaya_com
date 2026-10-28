// Video.js 10 oynatıcı paketi: Türkçe arayüz, varsayılan video görünümü ve Vimeo kaynağı.
// Derleme: `npm run build` → static_files/js/videojs/player.js (Django bu dosyayı sunar).
import '@videojs/html/i18n';
import '@videojs/html/i18n/locales/tr/register';
import '@videojs/html/video/player';
import '@videojs/html/video/skin';
import '@videojs/html/media/vimeo-video';

export { enableVimeoQuality } from './vimeo-quality.js';
