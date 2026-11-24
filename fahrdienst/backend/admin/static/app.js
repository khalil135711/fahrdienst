(() => {
'use strict';
const $ = s => document.querySelector(s);
// Sicheres Erzeugen von Elementen: Texte kommen nie als HTML in die Seite (Schutz vor XSS)
const el = (tag, props = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null) e.append(kid);
  return e;
};
const fill = (node, ...kids) => node.replaceChildren(...kids.flat().filter(k => k != null));

let token = sessionStorage.getItem('token');
let tab = 'live', map = null, layer = null, drivers = [], firstFit = true, timer = null, pwDriver = null;

const STATUS = {free: 'frei', busy: 'unterwegs', offline: 'offline', blocked: 'gesperrt'};
const RIDE = {requested: 'Anfrage', accepted: 'Angenommen', in_progress: 'Unterwegs',
  completed: 'Beendet', cancelled: 'Storniert', no_driver: 'Kein Fahrer'};
const COLOR = {free: '#1e9e5a', busy: '#e69a0c', offline: '#8a93a0', blocked: '#dc4638'};

const statusOf = d => d.active ? d.status : 'blocked';
const dt = iso => iso ? new Date(iso).toLocaleString('de-DE', {dateStyle: 'short', timeStyle: 'short'}) : '–';
const num = (v, suffix = '') => v == null ? '–' : v + suffix;
function ago(iso) {
  if (!iso) return 'nie';
  const s = (Date.now() - new Date(iso)) / 1000;
  if (s < 60) return 'gerade eben';
  if (s < 3600) return 'vor ' + Math.floor(s / 60) + ' Min.';
  if (s < 86400) return 'vor ' + Math.floor(s / 3600) + ' Std.';
  return new Date(iso).toLocaleDateString('de-DE');
}

async function api(path, {method = 'GET', body} = {}) {
  const r = await fetch(path, {
    method,
    headers: {'Content-Type': 'application/json', ...(token ? {Authorization: 'Bearer ' + token} : {})},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (r.status === 401 && token) { logout(); throw new Error('Bitte erneut anmelden'); }
  let data = null;
  try { data = await r.json(); } catch (_) {}
  if (!r.ok) throw new Error(errMsg(data, r.status));
  return data;
}
function errMsg(data, status) {
  if (data && typeof data.detail === 'string') return data.detail;
  if (data && Array.isArray(data.detail) && data.detail[0]) return 'Ungültige Eingabe: ' + data.detail[0].msg;
  return 'Fehler ' + status;
}

// ---------------------------------------------------------------- Anmeldung
function logout() {
  token = null;
  sessionStorage.clear();
  clearInterval(timer);
  $('#app').classList.add('hidden');
  $('#login').classList.remove('hidden');
  $('#password').value = '';
}

$('#loginForm').addEventListener('submit', async e => {
  e.preventDefault();
  $('#loginErr').textContent = '';
  try {
    const d = await api('/auth/login', {method: 'POST',
      body: {email: $('#email').value.trim(), password: $('#password').value}});
    if (d.role !== 'admin') throw new Error('Dieses Konto ist kein Administrator-Konto');
    token = d.token;
    sessionStorage.setItem('token', token);
    sessionStorage.setItem('name', d.name);
    start();
  } catch (err) { $('#loginErr').textContent = err.message; }
});
$('#btnLogout').addEventListener('click', logout);
$('#btnRefresh').addEventListener('click', () => load(true));

async function start() {
  $('#login').classList.add('hidden');
  $('#app').classList.remove('hidden');
  $('#who').textContent = sessionStorage.getItem('name') || '';
  initMap();
  await load();
  clearInterval(timer);
  timer = setInterval(load, 5000);
}

// ---------------------------------------------------------------- Karte
function initMap() {
  if (map) { setTimeout(() => map.invalidateSize(), 50); return; }
  try {
    map = L.map('map').setView([50.7374, 7.0982], 12);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '© OpenStreetMap-Mitwirkende'}).addTo(map);
    layer = L.layerGroup().addTo(map);
  } catch (e) { map = null; }  // Karte ist optional, der Rest funktioniert trotzdem
}

function renderMap() {
  if (!map) return;
  try {
    layer.clearLayers();
    const pts = [];
    for (const d of drivers) {
      if (d.lat == null || d.lng == null) continue;
      const st = statusOf(d);
      if (st === 'offline' || st === 'blocked') continue;  // nur aktive Fahrer zeigen
      const m = L.circleMarker([d.lat, d.lng], {radius: 10, color: '#fff', weight: 3,
        fillColor: COLOR[st], fillOpacity: 1});
      m.bindTooltip(d.name + ' (' + STATUS[st] + ', Position ' + ago(d.last_seen) + ')');
      m.addTo(layer);
      pts.push([d.lat, d.lng]);
    }
    if (firstFit && pts.length) { map.fitBounds(pts, {padding: [50, 50], maxZoom: 15}); firstFit = false; }
  } catch (e) { /* Die Karte ist optional: ein Kartenfehler darf den Rest der Seite nicht stoppen */ }
}

// ---------------------------------------------------------------- Rendering
function renderCards(o) {
  const card = (v, label, color) => el('div', {class: 'stat'},
    el('b', {style: 'color:' + color}, String(v)), el('span', {}, label));
  fill($('#cards'),
    card(o.rides_today, 'Fahrten heute', 'var(--blue)'),
    card(o.completed_today, 'Beendet heute', 'var(--blue)'),
    card(o.drivers_free, 'Fahrer frei', 'var(--green)'),
    card(o.drivers_busy, 'Fahrer unterwegs', 'var(--amber)'),
    card(o.drivers_offline, 'Fahrer offline', 'var(--grey)'),
    card(o.avg_rating == null ? '–' : o.avg_rating + ' ★', 'Ø Bewertung', 'var(--amber)'),
    card(o.pooled_today + ' / ' + o.shared_today, 'Zusammengelegt / geteilt angefragt (heute)', 'var(--blue)'),
    card(o.saved_km_30d + ' km', 'Gesparte Strecke durch Teilen (30 Tage)', 'var(--green)'),
    card('≈ ' + o.saved_cost_30d.toFixed(2) + ' €', 'Gesparte Kosten (30 Tage)', 'var(--green)'),
    card(o.revenue_today.toFixed(2) + ' €', 'Umsatz heute (beendete Fahrten)', 'var(--blue)'),
    card(o.partner_rides_today + ' / ' + o.partner_fees_today.toFixed(2) + ' €', 'Partnerfahrten heute / Gebühren', 'var(--amber)'),
    card(o.partner_fees_30d.toFixed(2) + ' €', 'Partnergebühren (30 Tage)', 'var(--amber)'));
}

function renderLive() {
  const order = {free: 0, busy: 1, offline: 2, blocked: 3};
  const sorted = [...drivers].sort((a, b) => order[statusOf(a)] - order[statusOf(b)] || a.name.localeCompare(b.name));
  fill($('#liveList'), sorted.length ? sorted.map(d => {
    const st = statusOf(d);
    return el('div', {class: 'row'},
      el('span', {class: 'dot ' + st}),
      el('div', {style: 'flex:1'}, el('div', {}, d.name),
        el('small', {}, d.vehicle + ' · Position ' + ago(d.last_seen))),
      el('span', {class: 'badge ' + st}, STATUS[st]));
  }) : el('p', {class: 'muted'}, 'Noch keine Fahrer angelegt.'));
}

function table(node, headers, rows, empty) {
  fill(node, el('thead', {}, el('tr', {}, headers.map(h => el('th', {}, h)))),
    el('tbody', {}, rows.length ? rows : el('tr', {}, el('td', {colspan: headers.length, class: 'muted'}, empty))));
}

function renderDrivers() {
  table($('#driversTable'),
    ['Fahrer', 'Fahrzeug', 'Gehört zu', 'Status', 'Bewertung', 'Fahrten', 'Kilometer', 'Ø km/h', 'Max km/h', 'Position', ''],
    drivers.map(d => {
      const st = statusOf(d);
      return el('tr', {},
        el('td', {}, el('div', {}, d.name), el('small', {class: 'muted'}, d.email)),
        el('td', {}, d.vehicle + ' · ' + d.plate, d.vehicle_type === 'wheelchair' ? el('span', {class: 'badge', style: 'margin-left:6px'}, '♿ Rollstuhl') : null),
        el('td', {}, d.company || 'Eigener Fahrer'),
        el('td', {}, el('span', {class: 'badge ' + st}, STATUS[st])),
        el('td', {}, d.rating_avg == null ? '–' : '★ ' + d.rating_avg + ' (' + d.rating_count + ')'),
        el('td', {}, String(d.rides)), el('td', {}, d.km + ' km'),
        el('td', {}, num(d.avg_speed)), el('td', {}, num(d.max_speed)),
        el('td', {}, ago(d.last_seen)),
        el('td', {style: 'white-space:nowrap'},
          el('button', {class: 'btn small ' + (d.active ? 'danger' : ''), onclick: () => toggle(d)},
            d.active ? 'Sperren' : 'Freigeben'), ' ',
          el('button', {class: 'btn small', onclick: () => openPw(d)}, 'Passwort')));
    }), 'Noch keine Fahrer. Legen Sie den ersten mit „Fahrer anlegen“ an.');
}

async function loadRides() {
  const rows = await api('/admin/rides?limit=50');
  table($('#ridesTable'), ['#', 'Status', 'Kunde', 'Fahrer', 'Strecke', 'Preis', 'Besonderheiten', 'Quittung', 'Angefragt', 'Beendet'],
    rows.map(r => el('tr', {},
      el('td', {}, String(r.id)), el('td', {}, el('span', {class: 'badge ' + r.status}, RIDE[r.status] || r.status)),
      el('td', {}, r.customer), el('td', {}, r.driver ? r.driver + (r.company ? ' (' + r.company + ')' : '') : '–'),
      el('td', {}, r.route || '–'),
      el('td', {}, r.price == null ? '–' : r.price.toFixed(2) + ' €' + (r.company ? ' (Servicegebühr)' : '')),
      el('td', {}, [r.vehicle_type === 'wheelchair' ? '♿ Rollstuhl' : null, r.payment_method === 'taxischein' ? 'Taxischein' : null,
        r.pooled ? 'zusammengelegt (−' + (r.saved_km || 0) + ' km)' : (r.shared ? 'geteilt angefragt' : null)].filter(Boolean).join(', ') || '–'),
      el('td', {}, r.receipt_no || '–'),
      el('td', {}, dt(r.requested_at)), el('td', {}, dt(r.finished_at)))), 'Noch keine Fahrten.');
}

async function loadRatings() {
  const rows = await api('/admin/ratings?limit=50');
  table($('#ratingsTable'), ['Bewertung', 'Fahrer', 'Kunde', 'Kommentar', 'Datum'],
    rows.map(r => el('tr', {},
      el('td', {}, el('span', {class: 'stars'}, '★'.repeat(r.stars) + '☆'.repeat(5 - r.stars))),
      el('td', {}, r.driver), el('td', {}, r.customer), el('td', {}, r.comment || '–'), el('td', {}, dt(r.created_at)))),
    'Noch keine Bewertungen.');
}

async function loadSpeed() {
  const limit = Math.max(10, Math.min(300, Number($('#limit').value) || 100));
  const rows = await api('/admin/speeding?limit_kmh=' + limit + '&hours=' + Number($('#hours').value));
  table($('#speedTable'), ['Zeit', 'Fahrer', 'Geschwindigkeit', 'Ort'],
    rows.map(r => el('tr', {},
      el('td', {}, dt(r.recorded_at)), el('td', {}, r.driver),
      el('td', {style: 'color:var(--red);font-weight:600'}, r.speed_kmh.toFixed(0) + ' km/h'),
      el('td', {}, el('a', {href: 'https://www.openstreetmap.org/?mlat=' + r.lat + '&mlon=' + r.lng + '#map=17/' + r.lat + '/' + r.lng,
        target: '_blank', rel: 'noopener noreferrer', style: 'color:var(--blue)'}, 'Karte öffnen')))),
    'Keine Überschreitungen im Zeitraum.');
}

// ---------------------------------------------------------------- Laden
async function load(force) {
  try {
    const days = Number($('#days').value);
    const [o, d] = await Promise.all([api('/admin/overview'), api('/admin/drivers?days=' + days)]);
    drivers = d;
    $('#globalErr').textContent = '';
    renderCards(o); renderLive(); renderMap(); renderDrivers();
    if (tab === 'rides') await loadRides();
    if (tab === 'ratings') await loadRatings();
    if (tab === 'speed') await loadSpeed();
    // Musik und Zeitungen nur beim Öffnen/Aktualisieren laden, nicht alle 5 Sekunden
    if (force && tab === 'music') await loadMusic();
    if (force && tab === 'news') await loadNews();
    if (force && tab === 'prices') await loadPrices();
    if (force && tab === 'companies') await loadCompanies();
  } catch (e) { $('#globalErr').textContent = e.message; }
}

$('#tabs').addEventListener('click', e => {
  const b = e.target.closest('button[data-tab]');
  if (!b) return;
  tab = b.dataset.tab;
  document.querySelectorAll('#tabs button').forEach(x => x.classList.toggle('on', x === b));
  document.querySelectorAll('[id^="tab-"]').forEach(p => p.classList.toggle('hidden', p.id !== 'tab-' + tab));
  if (tab === 'live' && map) setTimeout(() => map.invalidateSize(), 50);
  load(true);
});
$('#days').addEventListener('change', () => load());
$('#limit').addEventListener('change', () => loadSpeed().catch(e => $('#globalErr').textContent = e.message));
$('#hours').addEventListener('change', () => loadSpeed().catch(e => $('#globalErr').textContent = e.message));

// ---------------------------------------------------------------- Aktionen
async function toggle(d) {
  const msg = d.active ? d.name + ' sperren? Der Fahrer wird sofort abgemeldet und erhält keine Anfragen mehr.'
                       : d.name + ' wieder freigeben?';
  if (!confirm(msg)) return;
  try { await api('/admin/drivers/' + d.id, {method: 'PATCH', body: {active: !d.active}}); await load(); }
  catch (e) { $('#globalErr').textContent = e.message; }
}

$('#btnNew').addEventListener('click', async () => {
  $('#createForm').reset(); $('#createErr').textContent = '';
  try {
    const cs = await api('/admin/companies');
    fill($('#createCompany'), el('option', {value: ''}, 'Unser Unternehmen (eigener Fahrer)'),
      cs.filter(c => c.active).map(c => el('option', {value: c.id}, 'Partnerfirma: ' + c.name)));
  } catch (_) {}
  $('#dlgCreate').showModal();
});
$('#createCancel').addEventListener('click', () => $('#dlgCreate').close());
$('#createForm').addEventListener('submit', async e => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target));
  f.company_id = f.company_id ? Number(f.company_id) : null;
  try {
    await api('/admin/drivers', {method: 'POST', body: f});
    $('#dlgCreate').close();
    await load();
  } catch (err) { $('#createErr').textContent = err.message; }
});

function openPw(d) {
  pwDriver = d; $('#pwForm').reset(); $('#pwErr').textContent = '';
  $('#pwTitle').textContent = 'Neues Passwort für ' + d.name;
  $('#dlgPw').showModal();
}
$('#pwCancel').addEventListener('click', () => $('#dlgPw').close());
$('#pwForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    await api('/admin/drivers/' + pwDriver.id + '/password', {method: 'POST', body: {password: new FormData(e.target).get('password')}});
    $('#dlgPw').close();
  } catch (err) { $('#pwErr').textContent = err.message; }
});

// ---------------------------------------------------------------- Musik
let audio = null, audioBtn = null;
const dur = s => s == null ? '–' : Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
const size = b => b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.round(b / 1024) + ' KB';
const showErr = (sel, e) => { $(sel).textContent = e.message || String(e); };

function stopPreview() {
  if (audio) { audio.pause(); audio = null; }
  if (audioBtn) { audioBtn.textContent = '▶ Anhören'; audioBtn = null; }
}
function preview(t, btn) {
  const same = audioBtn === btn;
  stopPreview();
  if (same) return;
  audio = new Audio(t.stream_url);
  audioBtn = btn; btn.textContent = '■ Stopp';
  audio.addEventListener('ended', stopPreview);
  audio.play().catch(() => stopPreview());
}

async function loadMusic() {
  const libs = await api('/admin/music/libraries');
  const sel = $('#uploadLib'), flt = $('#trackFilter');
  const keepUp = sel.value, keepFlt = flt.value;
  fill(sel, libs.map(l => el('option', {value: l.id}, l.name)));
  fill(flt, el('option', {value: ''}, 'Alle Bibliotheken'), libs.map(l => el('option', {value: l.id}, l.name)));
  if (libs.some(l => String(l.id) === keepUp)) sel.value = keepUp;
  if (libs.some(l => String(l.id) === keepFlt)) flt.value = keepFlt;

  table($('#libTable'), ['Bibliothek', 'Beschreibung', 'Titel', 'Dauer', ''],
    libs.map(l => el('tr', {},
      el('td', {}, l.name), el('td', {class: 'muted'}, l.description || '–'),
      el('td', {}, String(l.tracks)), el('td', {}, Math.round(l.duration_s / 60) + ' Min.'),
      el('td', {}, el('button', {class: 'btn small danger', onclick: async () => {
        if (!confirm('Bibliothek „' + l.name + '“ mit allen ' + l.tracks + ' Titeln endgültig löschen?')) return;
        try { stopPreview(); await api('/admin/music/libraries/' + l.id, {method: 'DELETE'}); await loadMusic(); }
        catch (e) { showErr('#libErr', e); }
      }}, 'Löschen')))), 'Noch keine Bibliothek. Legen Sie oben die erste an.');

  const tracks = await api('/admin/music/tracks' + (flt.value ? '?library_id=' + flt.value : ''));
  table($('#trackTable'), ['Titel', 'Künstler', 'Bibliothek', 'Dauer', 'Größe', 'Lizenznachweis', ''],
    tracks.map(t => {
      const play = el('button', {class: 'btn small'}, '▶ Anhören');
      play.addEventListener('click', () => preview(t, play));
      return el('tr', {},
        el('td', {}, t.title), el('td', {}, t.artist || '–'), el('td', {}, t.library),
        el('td', {}, dur(t.duration_s)), el('td', {}, size(t.size_bytes)), el('td', {class: 'muted'}, t.license_note),
        el('td', {style: 'white-space:nowrap'}, play, ' ',
          el('button', {class: 'btn small danger', onclick: async () => {
            if (!confirm('„' + t.title + '“ löschen?')) return;
            try { stopPreview(); await api('/admin/music/tracks/' + t.id, {method: 'DELETE'}); await loadMusic(); }
            catch (e) { showErr('#uploadErr', e); }
          }}, 'Löschen')));
    }), 'Noch keine Titel.');
}

$('#libForm').addEventListener('submit', async e => {
  e.preventDefault(); $('#libErr').textContent = '';
  try {
    await api('/admin/music/libraries', {method: 'POST', body: Object.fromEntries(new FormData(e.target))});
    e.target.reset(); await loadMusic();
  } catch (err) { showErr('#libErr', err); }
});
$('#trackFilter').addEventListener('change', () => loadMusic().catch(err => showErr('#uploadErr', err)));
$('#uploadForm').addEventListener('submit', async e => {
  e.preventDefault();
  const out = $('#uploadErr'); out.className = 'muted'; out.textContent = 'Wird hochgeladen …';
  const fd = new FormData(e.target);
  try {
    const r = await fetch('/admin/music/tracks', {method: 'POST', headers: {Authorization: 'Bearer ' + token}, body: fd});
    let data = null; try { data = await r.json(); } catch (_) {}
    if (r.status === 401) { logout(); return; }
    if (!r.ok) throw new Error(errMsg(data, r.status));
    e.target.reset(); out.className = 'ok'; out.textContent = 'Hochgeladen: ' + data.title;
    await loadMusic();
  } catch (err) { out.className = 'err'; out.textContent = err.message; }
});

// ---------------------------------------------------------------- Zeitungen
async function loadNews() {
  const rows = await api('/admin/news');
  table($('#newsTable'), ['Zeitung', 'Feed-Adresse', 'Status', ''],
    rows.map(n => el('tr', {},
      el('td', {}, n.name), el('td', {class: 'muted', style: 'word-break:break-all'}, n.feed_url),
      el('td', {}, el('span', {class: 'badge ' + (n.active ? 'free' : 'blocked')}, n.active ? 'aktiv' : 'aus')),
      el('td', {style: 'white-space:nowrap'},
        el('button', {class: 'btn small', onclick: () => newsPreview(n)}, 'Vorschau'), ' ',
        el('button', {class: 'btn small', onclick: async () => {
          try { await api('/admin/news/' + n.id, {method: 'PATCH', body: {active: !n.active}}); await loadNews(); }
          catch (e) { showErr('#newsErr', e); }
        }}, n.active ? 'Ausschalten' : 'Einschalten'), ' ',
        el('button', {class: 'btn small danger', onclick: async () => {
          if (!confirm('„' + n.name + '“ entfernen?')) return;
          try { await api('/admin/news/' + n.id, {method: 'DELETE'}); await loadNews(); }
          catch (e) { showErr('#newsErr', e); }
        }}, 'Löschen')))), 'Noch keine Zeitung eingetragen.');
}
async function newsPreview(n) {
  const box = $('#newsPreview'); box.className = 'muted'; fill(box, 'Lädt …');
  try {
    const items = await api('/news/sources/' + n.id + '/items');
    box.className = '';
    fill(box, el('b', {}, n.name), items.length ? items.map(i => el('div', {class: 'row'},
      el('div', {style: 'flex:1'},
        /^https?:\/\//.test(i.link) ? el('a', {href: i.link, target: '_blank', rel: 'noopener noreferrer', style: 'color:var(--blue)'}, i.title) : i.title,
        i.summary ? el('div', {class: 'muted', style: 'font-size:13px'}, i.summary) : null),
      el('small', {}, i.published ? dt(i.published) : ''))) : el('p', {class: 'muted'}, 'Keine Meldungen im Feed.'));
  } catch (e) { box.className = 'err'; fill(box, e.message); }
}
$('#newsForm').addEventListener('submit', async e => {
  e.preventDefault(); $('#newsErr').textContent = '';
  try {
    await api('/admin/news', {method: 'POST', body: Object.fromEntries(new FormData(e.target))});
    e.target.reset(); await loadNews();
  } catch (err) { showErr('#newsErr', err); }
});

// ---------------------------------------------------------------- Preise und Teilen
async function loadPrices() {
  const rows = await api('/admin/settings');
  fill($('#priceFields'), rows.map(m => el('div', {},
    el('label', {}, m.label + (m.unit ? ' (' + m.unit + ')' : '')),
    m.type === 'text'
      ? el('input', {name: m.key, type: 'text', maxlength: 200, value: m.value, 'data-kind': 'text'})
      : el('input', {name: m.key, type: 'number', step: 'any', min: m.min, max: m.max, value: m.value, required: true}))));
}
$('#priceForm').addEventListener('submit', async e => {
  e.preventDefault();
  const out = $('#priceMsg'); out.className = 'muted'; out.textContent = 'Speichert …';
  const body = {};
  for (const inp of e.target.querySelectorAll('input[name]')) body[inp.name] = inp.dataset.kind === 'text' ? inp.value : Number(inp.value);
  try { await api('/admin/settings', {method: 'PUT', body}); out.className = 'ok'; out.textContent = 'Gespeichert. Gilt sofort für neue Anfragen.'; }
  catch (err) { out.className = 'err'; out.textContent = err.message; }
});

// ---------------------------------------------------------------- Firmen
const monthNow = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0'); };
async function loadCompanies() {
  const rows = await api('/admin/companies');
  table($('#companyTable'), ['Firma', 'Kontakt', 'Fahrer', 'Fahrten (30 Tage)', 'Gebühren (30 Tage)', 'Gebühr pro Fahrt', 'Status', ''],
    rows.map(co => el('tr', {},
      el('td', {}, el('div', {}, co.name), el('small', {class: 'muted'}, co.address || '')),
      el('td', {class: 'muted'}, co.contact || '–'), el('td', {}, String(co.drivers)),
      el('td', {}, String(co.rides_30d)), el('td', {}, co.fees_30d.toFixed(2) + ' €'),
      el('td', {}, co.effective_fee.toFixed(2) + ' €' + (co.fee_per_ride == null ? ' (Standard)' : '')),
      el('td', {}, el('span', {class: 'badge ' + (co.active ? 'free' : 'blocked')}, co.active ? 'aktiv' : 'aus')),
      el('td', {style: 'white-space:nowrap'},
        el('button', {class: 'btn small', onclick: () => statement(co)}, 'Abrechnung'), ' ',
        el('button', {class: 'btn small', onclick: () => setFee(co)}, 'Gebühr'), ' ',
        el('button', {class: 'btn small ' + (co.active ? 'danger' : ''), onclick: async () => {
          if (co.active && !confirm(co.name + ' ausschalten? Die Fahrer gehen offline und erhalten keine Anfragen mehr.')) return;
          try { await api('/admin/companies/' + co.id, {method: 'PATCH', body: {active: !co.active}}); await loadCompanies(); }
          catch (e) { showErr('#companyErr', e); }
        }}, co.active ? 'Ausschalten' : 'Einschalten')))), 'Noch keine Partnerfirma.');
}
async function setFee(co) {
  const v = prompt('Gebühr pro Fahrt für ' + co.name + ' in € (leer lassen = Standardgebühr):', co.fee_per_ride == null ? '' : co.fee_per_ride);
  if (v === null) return;
  const body = v.trim() === '' ? {use_default_fee: true} : {fee_per_ride: Number(v.replace(',', '.'))};
  try { await api('/admin/companies/' + co.id, {method: 'PATCH', body}); await loadCompanies(); }
  catch (e) { showErr('#companyErr', e); }
}
async function statement(co) {
  const box = $('#statementBox');
  const month = prompt('Monat der Abrechnung für ' + co.name + ' (JJJJ-MM):', monthNow());
  if (!month) return;
  box.className = 'muted'; fill(box, 'Lädt …');
  try {
    const d = await api('/admin/companies/' + co.id + '/statement?month=' + encodeURIComponent(month.trim()));
    box.className = '';
    const csv = '\ufeffFahrt;Quittung;Beendet;Kilometer;Gebühr in EUR\n' + d.items.map(i =>
      [i.ride_id, i.receipt_no || '', dt(i.finished_at), i.distance_km == null ? '' : String(i.distance_km).replace('.', ','), i.fee.toFixed(2).replace('.', ',')].join(';')).join('\n');
    const link = el('a', {href: URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'})), download: 'Abrechnung-' + d.company.replace(/[^\w-]+/g, '_') + '-' + d.month + '.csv', class: 'btn small'}, 'CSV herunterladen');
    fill(box, el('div', {style: 'margin-bottom:8px'}, el('b', {}, d.company + ', ' + d.month + ': '), d.rides + ' Fahrten, Gebühren gesamt ', el('b', {}, d.total_fee.toFixed(2) + ' €'), '  ', link));
    box.append(el('div', {class: 'tablewrap'}, (() => { const t = el('table'); table(t, ['Fahrt', 'Quittung', 'Beendet', 'Kilometer', 'Gebühr'],
      d.items.map(i => el('tr', {}, el('td', {}, String(i.ride_id)), el('td', {}, i.receipt_no || '–'), el('td', {}, dt(i.finished_at)),
        el('td', {}, i.distance_km == null ? '–' : i.distance_km + ' km'), el('td', {}, i.fee.toFixed(2) + ' €'))), 'Keine Fahrten in diesem Monat.'); return t; })()));
  } catch (e) { box.className = 'err'; fill(box, e.message); }
}
$('#companyForm').addEventListener('submit', async e => {
  e.preventDefault(); $('#companyErr').textContent = '';
  const f = Object.fromEntries(new FormData(e.target));
  f.fee_per_ride = f.fee_per_ride === '' ? null : Number(f.fee_per_ride);
  try { await api('/admin/companies', {method: 'POST', body: f}); e.target.reset(); await loadCompanies(); }
  catch (err) { showErr('#companyErr', err); }
});

// ---------------------------------------------------------------- Start
(async () => {
  if (!token) { $('#login').classList.remove('hidden'); return; }
  try {
    const me = await api('/auth/me');
    if (me.role !== 'admin') throw new Error('kein Admin');
    sessionStorage.setItem('name', me.name);
    start();
  } catch (_) { logout(); }
})();
})();
