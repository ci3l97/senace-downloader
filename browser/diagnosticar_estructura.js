/*
Diagnóstico del DOM de Consulta Ciudadana.
No descarga documentos. Genera un JSON pequeño con el contexto HTML de los
primeros enlaces para poder adaptar el exportador jerárquico sin adivinar.
*/
(() => {
  const links = [...document.querySelectorAll('a[href*="DownloadByGet"]')];
  if (!links.length) {
    console.error('No encontré enlaces DownloadByGet.');
    return;
  }

  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const describe = el => el ? {
    tag: el.tagName,
    id: el.id || '',
    class: typeof el.className === 'string' ? el.className : '',
    role: el.getAttribute?.('role') || '',
    ariaLabel: el.getAttribute?.('aria-label') || '',
    ariaLabelledBy: el.getAttribute?.('aria-labelledby') || '',
    text: clean(el.innerText).slice(0, 500)
  } : null;

  const samples = links.slice(0, Math.min(8, links.length)).map((a, idx) => {
    const ancestors = [];
    let el = a;
    for (let depth = 0; el && depth < 10; depth++, el = el.parentElement) {
      ancestors.push(describe(el));
    }

    const row = a.closest('tr');
    const previousRows = [];
    let p = row?.previousElementSibling;
    for (let k = 0; p && k < 5; k++, p = p.previousElementSibling) {
      previousRows.push(describe(p));
    }

    return {
      index: idx + 1,
      href: a.href,
      row: describe(row),
      ancestors,
      previousRows,
      outerHTML: (row || a).outerHTML.slice(0, 10000)
    };
  });

  const payload = {
    page: location.href,
    title: document.title,
    totalDownloadLinks: links.length,
    capturedAt: new Date().toISOString(),
    samples
  };

  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: 'application/json;charset=utf-8'
  });
  const dl = document.createElement('a');
  dl.href = URL.createObjectURL(blob);
  dl.download = 'senace_dom_diagnostico.json';
  document.body.appendChild(dl);
  dl.click();
  dl.remove();
  setTimeout(() => URL.revokeObjectURL(dl.href), 1000);
  console.log(`Diagnóstico creado. Enlaces detectados: ${links.length}`);
})();
