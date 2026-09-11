const $ = (id) => document.getElementById(id);
let config = null;
let accessToken = ''; // Kept only in memory, never in URLs or browser storage.
let polling = false;
const labels = { queued: 'Đang chờ', running: 'Đang dịch', done: 'Hoàn tất', error: 'Cần kiểm tra', cancelled: 'Đã hủy' };

function showError(id, message = '') {
  $(id).textContent = message;
  $(id).hidden = !message;
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers);
  headers.set('X-DocWeave', '1');
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  let response;
  try { response = await fetch(path, { ...options, headers }); }
  catch { throw new Error('Mất kết nối với máy chủ. Kiểm tra máy chủ rồi thử lại.'); }
  if (!response.ok) {
    let message = `Yêu cầu thất bại (${response.status}).`;
    try { const body = await response.json(); if (typeof body.detail === 'string') message = body.detail; } catch {}
    if (response.status === 401 && !$('auth-dialog').open) $('auth-dialog').showModal();
    throw new Error(message);
  }
  return response;
}

function fileChanged(file) {
  showError('form-error');
  if (!file) { $('file-title').textContent = 'Thả tài liệu vào đây'; $('file-description').textContent = 'hoặc bấm để chọn tệp PDF'; return; }
  $('file-title').textContent = file.name;
  $('file-description').textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB · Bấm để đổi tệp`;
  if (!file.name.toLowerCase().endsWith('.pdf')) showError('form-error', 'Hãy chọn tệp có định dạng PDF.');
  else if (config && file.size > config.max_upload_mb * 1024 * 1024) showError('form-error', `Tệp vượt giới hạn ${config.max_upload_mb} MB.`);
}
$('file').addEventListener('change', () => fileChanged($('file').files[0]));
['dragenter', 'dragover'].forEach(name => $('dropzone').addEventListener(name, event => { event.preventDefault(); $('dropzone').classList.add('dragging'); }));
['dragleave', 'drop'].forEach(name => $('dropzone').addEventListener(name, event => { event.preventDefault(); $('dropzone').classList.remove('dragging'); }));
$('dropzone').addEventListener('drop', event => {
  if (event.dataTransfer.files.length !== 1) return showError('form-error', 'Mỗi lần chỉ chọn một tài liệu PDF.');
  $('file').files = event.dataTransfer.files;
  fileChanged($('file').files[0]);
});
$('swap').addEventListener('click', () => { const current = $('lang-in').value; $('lang-in').value = $('lang-out').value; $('lang-out').value = current; });

function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

function renderJobs(jobs) {
  $('count').textContent = jobs.length;
  if (!jobs.length) return;
  const fragment = document.createDocumentFragment();
  for (const job of jobs) {
    const card = element('article', 'job');
    const top = element('div', 'job-top');
    const title = element('h3', 'job-title', job.filename);
    top.append(title, element('span', `badge ${job.status}`, labels[job.status] || job.status));
    const language = (code) => config?.languages[code] || code;
    const meta = element('p', 'job-meta', `${job.pages} trang · ${language(job.lang_in)} → ${language(job.lang_out)} · ${new Date(job.created * 1000).toLocaleString('vi-VN')}`);
    const stage = element('p', 'job-stage', job.stage);
    card.append(top, meta, stage);
    if (job.status === 'running' || job.status === 'queued') {
      const progress = element('progress'); progress.max = 100; progress.value = job.progress;
      progress.setAttribute('aria-label', `Tiến độ ${job.filename}`);
      stage.textContent += ` · ${Math.round(job.progress)}%`;
      card.append(progress);
    }
    const actions = element('div', 'job-actions');
    if (job.status === 'done') {
      for (const [kind, label] of [['translated', '↓ Tải bản dịch'], ['bilingual', '↓ Tải song ngữ']]) {
        const button = element('button', '', label); button.type = 'button';
        button.addEventListener('click', async () => {
          button.disabled = true;
          try {
            const response = await api(`/api/jobs/${job.id}/download/${kind}`);
            const url = URL.createObjectURL(await response.blob());
            const link = element('a'); link.href = url; link.download = job.filename.replace(/\.pdf$/i, '') + `-${kind}.pdf`;
            document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
          } catch (error) { showError('history-error', error.message); }
          finally { button.disabled = false; }
        });
        actions.append(button);
      }
    } else if (job.status === 'running' || job.status === 'queued') {
      const cancel = element('button', 'cancel', 'Hủy tác vụ'); cancel.type = 'button';
      cancel.addEventListener('click', async () => {
        cancel.disabled = true;
        try { await api(`/api/jobs/${job.id}/cancel`, { method: 'POST' }); await refresh(); }
        catch (error) { showError('history-error', error.message); cancel.disabled = false; }
      });
      actions.append(cancel);
    }
    if (actions.childElementCount) card.append(actions);
    fragment.append(card);
  }
  $('jobs').replaceChildren(fragment);
}

async function refresh() {
  if (polling || !config) return;
  polling = true;
  try {
    const jobs = await (await api('/api/jobs')).json();
    if (!jobs.length && $('jobs').querySelector('.job')) {
      const empty = element('div', 'empty'); empty.append(element('h3', '', 'Chưa có tài liệu nào'), element('p', '', 'Tải PDF lên để bắt đầu. Tệp hết hạn được tự động dọn.'));
      $('jobs').replaceChildren(empty);
    }
    // Avoid replacing focused controls on every poll.
    const serialized = JSON.stringify(jobs);
    if ($('jobs').dataset.state !== serialized) { renderJobs(jobs); $('jobs').dataset.state = serialized; }
    showError('history-error'); $('connection').textContent = 'Máy chủ đang hoạt động';
  } catch (error) { showError('history-error', error.message); $('connection').textContent = 'Kết nối cần kiểm tra'; }
  finally { polling = false; }
}

$('translate-form').addEventListener('submit', async event => {
  event.preventDefault(); showError('form-error');
  if (!config) return;
  const file = $('file').files[0];
  if (!file) return showError('form-error', 'Hãy chọn một tài liệu PDF.');
  if (file.size > config.max_upload_mb * 1024 * 1024) return showError('form-error', `Tệp tối đa ${config.max_upload_mb} MB.`);
  if ($('lang-in').value === $('lang-out').value) return showError('form-error', 'Ngôn ngữ gốc và ngôn ngữ đích cần khác nhau.');
  if (!config.server_key) return showError('form-error', 'Backend chưa cấu hình OPENROUTER_API_KEY. Hãy điền khóa trong file .env rồi khởi động lại máy chủ.');
  $('submit').disabled = true; $('submit').firstElementChild.textContent = 'Đang tải tài liệu…';
  try {
    await api('/api/jobs', { method: 'POST', body: new FormData($('translate-form')) });
    $('file').value = ''; fileChanged(null);
    await refresh();
    $('history-title').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'center' });
  } catch (error) { showError('form-error', error.message); }
  finally { $('submit').disabled = false; $('submit').firstElementChild.textContent = 'Dịch tài liệu'; }
});

async function initialize() {
  config = await (await api('/api/config')).json();
  for (const [id, selected] of [['lang-in', 'en'], ['lang-out', 'vi']]) {
    $(id).replaceChildren(...Object.entries(config.languages).map(([code, label]) => new Option(label, code, code === selected, code === selected)));
  }
  $('limits').textContent = `Tối đa ${config.max_upload_mb} MB · ${config.max_pages} trang`;
  $('retention').textContent = `Tệp được tự động dọn sau ${config.retention_hours} giờ.`;
  $('model').textContent = `Model dịch: ${config.model}`;
  $('credentials').classList.toggle('missing', !config.server_key);
  if (!config.server_key) $('credentials').querySelector('p').textContent = 'Backend chưa sẵn sàng: hãy cấu hình OPENROUTER_API_KEY trong file .env.';
  $('submit').disabled = false;
  await refresh();
}
$('refresh').addEventListener('click', async () => { try { if (config) await refresh(); else await initialize(); } catch (error) { showError('history-error', error.message); } });
$('auth-form').addEventListener('submit', async event => {
  event.preventDefault(); accessToken = $('access-token').value.trim();
  try { await initialize(); $('access-token').value = ''; $('auth-dialog').close(); showError('auth-error'); }
  catch (error) { accessToken = ''; showError('auth-error', error.message); }
});
$('auth-dialog').addEventListener('cancel', event => event.preventDefault());
initialize().catch(error => { showError('history-error', error.message); $('connection').textContent = 'Chưa sẵn sàng'; });
setInterval(() => { if (!document.hidden && !$('auth-dialog').open) refresh(); }, 2000);
