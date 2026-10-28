// Video.js kalite menüsü, ortam öğesinde `videoRenditions` listesi bekler; Vimeo eklentisi bunu sağlamıyor.
// Liste Vimeo Player API'sinden (getQualities / setQuality / qualitychange) doldurulur.
// Kalite seçimi Vimeo'da ücretli plan ister; API reddederse liste boş kalır ve menü görünmez.

const NAMED_HEIGHTS = { '4k': 2160, '2k': 1440 };

function heightOf(qualityId) {
  return NAMED_HEIGHTS[qualityId] ?? parseInt(qualityId, 10);
}

class VimeoRenditionList extends EventTarget {
  #items = [];
  #select;

  constructor(select) {
    super();
    this.#select = select;
  }

  [Symbol.iterator]() {
    return this.#items.values();
  }

  get length() {
    return this.#items.length;
  }

  getRenditionById(id) {
    return this.#items.find((rendition) => rendition.id === `${id}`) ?? null;
  }

  // -1 otomatik kalite demektir.
  get selectedIndex() {
    return this.#items.findIndex((rendition) => rendition.selected);
  }

  set selectedIndex(index) {
    this.#select(this.#items[index]?.id ?? 'auto');
  }

  update(qualities) {
    this.#items = qualities
      .filter((quality) => quality.id !== 'auto' && heightOf(quality.id))
      .map((quality) => {
        const height = heightOf(quality.id);
        return { id: quality.id, height, width: Math.round((height * 16) / 9), selected: quality.active, active: quality.active };
      });
    this.dispatchEvent(new Event('change'));
  }
}

/** `<vimeo-video>` sayfaya eklenmeden önce çağrılır; `preferred` (ör. "720p") varsa ilk yüklemede seçilir. */
export function enableVimeoQuality(media, preferred) {
  const engine = () => media.adapter.engine;
  const refresh = () =>
    engine()
      ?.getQualities()
      .then((qualities) => list.update(qualities))
      .catch(() => {});
  const list = new VimeoRenditionList((id) => engine()?.setQuality(id).then(refresh).catch(() => {}));
  let initialized = false;

  media.videoRenditions = list;
  media.addEventListener('loadedmetadata', async () => {
    const player = engine();
    if (!player || initialized) return refresh();
    initialized = true;
    player.on('qualitychange', refresh);
    try {
      const qualities = await player.getQualities();
      if (preferred && qualities.some((quality) => quality.id === preferred)) await player.setQuality(preferred);
    } catch {
      return;
    }
    refresh();
  });
}
