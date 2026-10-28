import { copyFile, rm } from 'node:fs/promises';
import * as esbuild from 'esbuild';

const outdir = '../static_files/js/videojs';
const KEEP_LOCALES = new Set(['tr']);

// Site dili Türkçe ve Türkçe paket başta kaydediliyor; diğer dillerin isteğe bağlı paketleri boş modülle değiştirilir.
const onlyTurkishLocale = {
  name: 'only-turkish-locale',
  setup(build) {
    build.onResolve({ filter: /i18n\/locales\/[\w-]+\.js$/ }, (args) => {
      const locale = args.path.match(/locales\/([\w-]+)\.js$/)[1];
      if (args.kind !== 'dynamic-import' || KEEP_LOCALES.has(locale)) return undefined;
      return { path: locale, namespace: 'empty-locale' };
    });
    build.onLoad({ filter: /.*/, namespace: 'empty-locale' }, () => ({ contents: 'export default {};', loader: 'js' }));
  },
};

await rm(outdir, { recursive: true, force: true });
await esbuild.build({
  entryPoints: ['src/player.js'],
  outdir,
  bundle: true,
  format: 'esm',
  minify: true,
  target: ['es2022'],
  legalComments: 'linked',
  plugins: [onlyTurkishLocale],
  logLevel: 'info',
});

// Stüdyo'nun sürükle-bırak sıralaması: SortableJS hazır derlenmiş haliyle kopyalanır.
await copyFile('node_modules/sortablejs/Sortable.min.js', '../static_files/js/sortable.min.js');
