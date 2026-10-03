/* Copia del exportador principal para la carpeta browser/. */
(() => {
  const LINK_SELECTOR = 'a[href*="DownloadByGet"]';
  const normalize = value => String(value || '').replace(/\s+/g, ' ').trim();
  const cleanName = value => normalize(value).replace(/\bDescargar\b/gi, '').trim();
  const seen = new Set(), documents = [];
  let chapter = '', subchapter = '';
  const addDocument = (link, route, suggestedName) => {
    let parsed;
    try { parsed = new URL(link.href, location.href); } catch (_) { return; }
    if (parsed.hostname !== 'eva.senace.gob.pe' || !['https:', 'http:'].includes(parsed.protocol)) return;
    const docId = parsed.searchParams.get('docId') || '', key = docId || parsed.href;
    if (seen.has(key)) return;
    seen.add(key);
    const number = documents.length + 1;
    const fallback = cleanName(link.parentElement?.innerText) || cleanName(link.innerText) || `Documento ${number}`;
    const name = cleanName(suggestedName) || fallback;
    documents.push({numero: number, nombre: `${number}. ${name.replace(/^\d+[.)]\s*/, '')}`, url: parsed.href, docId, ruta: route.filter(Boolean), tipo: 'auto'});
  };
  const tables = [...document.querySelectorAll('table')].filter(table => table.querySelector(LINK_SELECTOR));
  for (const table of tables) for (const row of table.querySelectorAll('tr')) {
    const cells = [...row.children].filter(element => element.tagName === 'TD');
    if (!cells.length) continue;
    const links = [...row.querySelectorAll(LINK_SELECTOR)];
    if (links.length) {
      const nameCell = cells.find(cell => !cell.querySelector('a,button,input') && normalize(cell.innerText));
      for (const link of links) addDocument(link, [chapter, subchapter], nameCell?.innerText);
      continue;
    }
    const texts = cells.map(cell => normalize(cell.innerText)).filter(Boolean);
    const codeIndex = texts.findIndex(text => /^\d+(?:\.\d+)*$/.test(text));
    if (codeIndex < 0) continue;
    const code = texts[codeIndex];
    const title = texts.slice(codeIndex + 1).find(text => !/^Descargar Capitulo$/i.test(text));
    if (!title) continue;
    if (code.includes('.')) subchapter = title;
    else { chapter = title; subchapter = ''; }
  }
  for (const link of document.querySelectorAll(LINK_SELECTOR)) addDocument(link, [], cleanName(link.closest('tr')?.innerText));
  if (!documents.length) { console.error('No encontré enlaces DownloadByGet. Abre la pestaña de descargas y espera a que termine de cargar.'); return; }
  const routed = documents.filter(document => document.ruta.length).length;
  if (!confirm(`Se exportarán ${documents.length} documentos únicos. ${routed} tienen capítulo/subcapítulo detectado. ¿Continuar?`)) return;
  const bodyLines = String(document.body?.innerText || '').split(/\r?\n/).map(normalize).filter(Boolean);
  const caseIndex = bodyLines.findIndex(line => /^[A-Z]+(?:-[A-Z0-9]+)+-\d{5}-\d{4}$/i.test(line));
  const detailTitle = caseIndex >= 0 ? (bodyLines[caseIndex + 1] || '').replace(/\s+-\s+\d{2}\/\d{2}\/\d{4}(?:\s+\d{2}:\d{2}:\d{2})?\s*$/, '') : '';
  const headingTitle = [...document.querySelectorAll('h1,h2,h3,h4,.card-title,.modal-title')].map(element => normalize(element.innerText)).find(text => text && !/consulta ciudadana|descargar documentos/i.test(text) && text.length < 220);
  const projectTitle = prompt('Nombre del expediente/proyecto para la carpeta de salida:', detailTitle || headingTitle || 'Expediente SENACE') || 'Expediente SENACE';
  const manifest = {schema_version: 1, source: 'senace-consulta-ciudadana', portal_url: location.href, project_title: projectTitle, exported_at: new Date().toISOString(), documents};
  const blob = new Blob([JSON.stringify(manifest, null, 2)], {type: 'application/json;charset=utf-8'});
  const download = document.createElement('a');
  download.href = URL.createObjectURL(blob); download.download = 'manifest.json'; document.body.appendChild(download); download.click(); download.remove();
  setTimeout(() => URL.revokeObjectURL(download.href), 1000);
  console.log(`LISTO: ${documents.length} documentos; ${routed} con ruta. Archivo: manifest.json`);
  console.table(documents.slice(0, 10));
})();
