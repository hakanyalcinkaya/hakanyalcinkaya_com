// HLS kaliteleri yüklendiğinde istenen yükseklik bir kez seçilir; sonra kullanıcının seçimine dokunulmaz.
// Liste (videoRenditions) hls.js manifesti okuyunca oluşur; bu yüzden meta veri yüklenince seçilir.
// Video.js kalite menüsü listeyi kendisi gösterir; bu yalnız açılıştaki varsayılanı belirler.

export function preferQuality(media, height) {
  let applied = false;
  const apply = () => {
    const list = media.videoRenditions;
    if (applied || !list) return;
    const index = [...list].findIndex((rendition) => rendition.height === height);
    if (index === -1) return;
    applied = true;
    list.selectedIndex = index;
  };
  media.addEventListener('loadedmetadata', apply);
  media.addEventListener('canplay', apply);
}
