(function () {
  if (window.__lawagentFallbackLoaded) return
  window.__lawagentFallbackLoaded = true

  function text(value) {
    return String(value == null ? '' : value)
  }

  function escapeHtml(value) {
    return text(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;')
  }

  function querySelector(selector) {
    return document.querySelector(selector)
  }

  function queryAll(selector) {
    return Array.from(document.querySelectorAll(selector))
  }

  function setPanel(name) {
    queryAll('[data-lawagent-tab]').forEach(function (tab) {
      tab.setAttribute('aria-selected', String(tab.dataset.lawagentTab === name))
    })
    queryAll('[data-lawagent-panel]').forEach(function (panel) {
      panel.classList.toggle('mobile-active', panel.dataset.lawagentPanel === name)
    })
  }

  function setTextareaValue(value) {
    var textarea = querySelector('[data-lawagent-query]')
    if (!textarea) return
    textarea.value = value
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
    textarea.dispatchEvent(new Event('change', { bubbles: true }))
    textarea.focus()
  }

  function setBusy(isBusy) {
    var button = querySelector('[data-lawagent-submit]')
    if (!button) return
    button.disabled = isBusy
    button.textContent = isBusy ? '研究中…' : '开始研究 ↗'
  }

  function showAnswer(result) {
    var scroll = querySelector('.conversation-scroll')
    if (scroll) {
      scroll.innerHTML =
        '<article class="answer-sheet">' +
        '<header><span>研究意见</span><b>' +
        (result.clarification ? '需要补充事实' : '证据校验完成') +
        '</b></header>' +
        '<div class="answer-rule"></div>' +
        '<p>' +
        escapeHtml(result.clarification || result.answer || '未生成回答。') +
        '</p>' +
        '<footer>本回答用于法律信息检索与辅助分析，不替代执业律师的正式意见。</footer>' +
        '</article>'
    }
  }

  function renderEvidence(evidence) {
    var summary = querySelector('[data-lawagent-evidence-summary]')
    if (summary) {
      summary.innerHTML =
        '<div><b>' +
        (evidence.length || '—') +
        ' 条</b><span>已进入回答证据集</span></div>'
    }
    var list = querySelector('[data-lawagent-evidence-list]')
    if (!list) return
    if (!evidence.length) {
      list.innerHTML = '<div class="empty-rail">未检索到可展示证据。</div>'
      return
    }
    list.innerHTML = evidence
      .map(function (item, index) {
        return (
          '<button class="evidence-card' +
          (index === 0 ? ' active' : '') +
          '" type="button" data-lawagent-evidence-card="' +
          escapeHtml(item.article_id) +
          '">' +
          '<span class="evidence-index">0' +
          (index + 1) +
          '</span>' +
          '<div class="evidence-title"><b>' +
          escapeHtml(item.law_name) +
          '</b><span>↗</span></div>' +
          '<strong>' +
          escapeHtml(item.article_number) +
          '</strong>' +
          '<p>' +
          escapeHtml(item.content) +
          '</p>' +
          '<footer><span>✓ 现行有效</span><em>' +
          Math.round(Number(item.score || 0) * 100) +
          '% 匹配</em></footer>' +
          '</button>'
        )
      })
      .join('')
  }

  function renderTrace(events) {
    var log = querySelector('[data-lawagent-event-log]')
    if (!log) return
    log.innerHTML =
      '<header><span>运行日志</span><b>' +
      events.length +
      ' EVENTS</b></header>' +
      events
        .slice(-5)
        .map(function (event) {
          return (
            '<div><time>' +
            String(event.sequence).padStart(2, '0') +
            '</time><p>' +
            escapeHtml(event.summary) +
            '</p></div>'
          )
        })
        .join('')
  }

  async function submitResearch() {
    var textarea = querySelector('[data-lawagent-query]')
    var query = textarea ? textarea.value.trim() : ''
    if (query.length < 2) {
      if (textarea) textarea.focus()
      return
    }
    setBusy(true)
    try {
      var response = await fetch('/api/v1/chat', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ message: query }),
      })
      if (!response.ok) throw new Error('HTTP ' + response.status)
      var payload = await response.json()
      var result = payload.result || {}
      showAnswer(result)
      renderEvidence(result.evidence || [])
      renderTrace(result.events || [])
    } catch (error) {
      var scroll = querySelector('.conversation-scroll')
      if (scroll) {
        scroll.innerHTML =
          '<div class="error-card" role="alert"><b>暂时无法完成研究</b><span>请检查后端服务和网络连接后重试。</span></div>'
      }
    } finally {
      setBusy(false)
    }
  }

  function attachLawAgentFallback() {
    if (document.__lawagentFallbackAttached) return
    document.__lawagentFallbackAttached = true

  document.addEventListener(
    'click',
    function (event) {
      var target = event.target
      if (!(target instanceof Element)) return
      var promptButton = target.closest('[data-lawagent-prompt]')
      if (promptButton) {
        event.preventDefault()
        setTextareaValue(promptButton.getAttribute('data-lawagent-prompt') || '')
        return
      }
      var submitButton = target.closest('[data-lawagent-submit]')
      if (submitButton) {
        event.preventDefault()
        submitResearch()
        return
      }
      var tab = target.closest('[data-lawagent-tab]')
      if (tab) {
        event.preventDefault()
        setPanel(tab.getAttribute('data-lawagent-tab') || 'chat')
        return
      }
      var evidence = target.closest('[data-lawagent-evidence-card]')
      if (evidence) {
        event.preventDefault()
        queryAll('[data-lawagent-evidence-card]').forEach(function (card) {
          card.classList.toggle('active', card === evidence)
        })
      }
    },
    true,
  )

  document.addEventListener('keydown', function (event) {
    if (
      event.key === 'Enter' &&
      (event.ctrlKey || event.metaKey) &&
      event.target instanceof Element &&
      event.target.matches('[data-lawagent-query]')
    ) {
      event.preventDefault()
      submitResearch()
    }
  })

  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attachLawAgentFallback)
  } else {
    attachLawAgentFallback()
  }
})()
