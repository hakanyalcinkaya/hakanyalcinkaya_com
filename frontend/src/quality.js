// HLS kaliteleri yüklendiğinde istenen kalite bir kez seçilir; sonra kullanıcının seçimine dokunulmaz.
// `height` bir yükseklik (ör. 720) ya da "highest" olabilir. Liste (videoRenditions) hls.js manifesti okuyunca
// oluşur; bu yüzden meta veri yüklenince seçilir. Video.js kalite menüsü yalnız açılıştaki varsayılanı buradan alır.

export function preferQuality(media, height) {
  let applied = false;
  const apply = () => {
    const list = media.videoRenditions;
    if (applied || !list || !list.length) return;
    const renditions = [...list];
    const index =
      height === 'highest'
        ? renditions.reduce((best, rendition, i) => (rendition.height > renditions[best].height ? i : best), 0)
        : renditions.findIndex((rendition) => rendition.height === height);
    if (index === -1) return;
    applied = true;
    list.selectedIndex = index;
  };
  media.addEventListener('loadedmetadata', apply);
  media.addEventListener('canplay', apply);
}
