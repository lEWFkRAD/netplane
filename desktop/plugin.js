/**
 * NetPlane — self-hosted Tailscale control plane (Headscale) dashboard.
 * Talks to the netplane plugin backend via ctx.rest (/api/plugins/netplane).
 */

import {
  Badge,
  Button,
  Codicon,
  EmptyState,
  ErrorState,
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  StatusDot,
  cn,
  haptic,
  host,
  useMutation,
  usePluginI18n,
  useQuery,
  useQueryClient
} from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useState } from 'react'

const ID = 'netplane'

function fmtAgo(iso) {
  if (!iso) return '—'
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 90) return 'just now'
  if (s < 5400) return `${Math.round(s / 60)}m ago`
  if (s < 86400 * 7) return `${Math.round(s / 3600)}h ago`
  return new Date(iso).toLocaleDateString()
}

function fmtExpiry(iso) {
  if (!iso) return '—'
  const date = new Date(iso)
  const seconds = (date.getTime() - Date.now()) / 1000
  if (!Number.isFinite(seconds)) return 'invalid date'
  if (seconds <= 0) return `expired ${fmtAgo(iso)}`
  if (seconds < 5400) return `in ${Math.max(1, Math.round(seconds / 60))}m`
  if (seconds < 86400 * 7) return `in ${Math.round(seconds / 3600)}h`
  return `on ${date.toLocaleDateString()}`
}

function StatusCard({ status }) {
  const svc = status?.checks?.headscale_service
  const svcUp = svc === 'active'
  return jsxs('div', {
    className: 'flex flex-wrap items-center gap-3 rounded-md border border-(--ui-stroke-secondary) px-3 py-2 text-sm',
    children: [
      jsx(StatusDot, { status: svcUp ? 'ok' : 'error' }),
      jsxs('span', { className: 'font-medium', children: ['Headscale ', svcUp ? 'running' : svc] }),
      jsx('span', { className: 'text-(--ui-text-tertiary)', children: `nodes: ${status?.nodes_online ?? '?'} online / ${status?.nodes_total ?? '?'} total` }),
      jsx('span', { className: 'text-(--ui-text-quaternary) text-xs', children: status?.control_url || '' })
    ]
  })
}

function NodeRow({ n }) {
  const qc = useQueryClient()
  const expire = useMutation({
    mutationFn: () => ctxRest(`/nodes/${n.id}/expire`, { method: 'POST' }),
    onSuccess: () => {
      haptic('tap')
      qc.invalidateQueries({ queryKey: ['netplane', 'nodes'] })
    },
    onError: (e) => host.notify({ kind: 'error', message: `expire failed: ${e?.message || e}` })
  })
  return jsxs('div', {
    className: 'flex items-center gap-2 border-b border-(--ui-stroke-secondary) px-3 py-1.5 text-sm last:border-b-0',
    children: [
      jsx(StatusDot, { status: n.online ? 'ok' : 'offline' }),
      jsx('span', { className: 'w-40 truncate font-medium', children: n.given_name || n.hostname }),
      jsx('span', { className: 'w-32 text-(--ui-text-tertiary) font-mono text-xs', children: n.ips[0] || '' }),
      jsx('span', { className: 'w-24 text-(--ui-text-quaternary) text-xs', children: n.user }),
      jsx('span', { className: 'flex-1 text-(--ui-text-quaternary) text-xs', children: fmtAgo(n.last_seen) }),
      jsx(Button, {
        variant: 'ghost',
        size: 'sm',
        className: 'text-(--ui-text-quaternary)',
        disabled: expire.isPending,
        onClick: () => {
          const name = n.given_name || n.hostname
          if (window.confirm(`Expire node ${name}? It will need to authenticate again.`)) {
            expire.mutate()
          }
        },
        children: 'expire'
      })
    ]
  })
}

function PreauthRow({ k }) {
  return jsxs('div', {
    className: 'flex items-center gap-2 border-b border-(--ui-stroke-secondary) px-3 py-1.5 text-sm last:border-b-0',
    children: [
      jsx('span', { className: 'w-44 truncate text-xs text-(--ui-text-tertiary)', children: k.user || `key #${k.id}` }),
      jsx(Badge, { tone: k.used ? 'neutral' : 'success', children: k.used ? 'used' : 'fresh' }),
      k.reusable ? jsx(Badge, { tone: 'neutral', children: 'reusable' }) : null,
      jsx('span', { className: 'flex-1 text-(--ui-text-quaternary) text-xs', children: `expires ${fmtExpiry(k.expiration)} · created ${fmtAgo(k.created)}` })
    ]
  })
}

let ctxRef = null
function ctxRest(path, opts) {
  return ctxRef.rest(path, opts)
}

function SetupPanel() {
  const qc = useQueryClient()
  const [options, setOptions] = useState({ server_url: '', tls_mode: 'letsencrypt', acme_email: '', base_domain: 'tailnet.internal', headscale_user: 'hermes' })
  const [plan, setPlan] = useState(null)
  const [installed, setInstalled] = useState(false)
  const preview = useMutation({
    mutationFn: (values) => ctxRest('/setup/plan', { method: 'POST', body: values }),
    onSuccess: (result) => setPlan(result),
    onError: () => setPlan(null)
  })
  const install = useMutation({
    mutationFn: (values) => ctxRest('/setup/install', { method: 'POST', body: { ...values, confirmed: true } }),
    onSuccess: () => {
      setInstalled(true)
      setPlan(null)
      qc.invalidateQueries({ queryKey: ['netplane'] })
      host.notify({ kind: 'success', message: 'Headscale installed and configured. Its API key is saved in Hermes.' })
    }
  })
  const busy = preview.isPending || install.isPending
  const change = (name, value) => {
    setOptions({ ...options, [name]: value })
    setPlan(null)
    preview.reset()
    install.reset()
  }
  const field = (label, name, type = 'text', placeholder = '') => jsxs('label', {
    className: 'flex flex-col gap-1 text-xs',
    children: [
      label,
      jsx('input', { type, value: options[name], placeholder, disabled: busy || installed,
        onChange: (event) => change(name, event.target.value),
        className: 'rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1.5 text-sm' })
    ]
  })
  const error = install.error || preview.error
  return jsxs('details', {
    className: 'rounded-md border border-(--ui-stroke-secondary) p-3',
    children: [
      jsx('summary', { className: 'cursor-pointer text-sm font-medium', children: 'Install and configure Headscale' }),
      jsxs('div', { className: 'mt-3 flex flex-col gap-3', children: [
        jsx('p', { className: 'text-xs text-(--ui-text-tertiary)', children: 'Fresh installation on the Linux host running Hermes: Debian 12+ or Ubuntu 22.04+, systemd, amd64 or arm64. Requires root or noninteractive sudo. Existing installations are preserved and must be configured separately.' }),
        field('Public control-plane URL', 'server_url', 'url', 'https://headscale.example.com'),
        jsxs('label', { className: 'flex flex-col gap-1 text-xs', children: [
          'HTTPS setup',
          jsxs('select', { value: options.tls_mode, disabled: busy || installed, onChange: (event) => change('tls_mode', event.target.value), className: 'rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1.5 text-sm', children: [
            jsx('option', { value: 'letsencrypt', children: "Automatic certificate with Let's Encrypt" }),
            jsx('option', { value: 'reverse_proxy', children: 'I already have an HTTPS reverse proxy' })
          ] })
        ] }),
        options.tls_mode === 'letsencrypt' ? field("Let's Encrypt contact email", 'acme_email', 'email') : null,
        field('MagicDNS domain', 'base_domain'),
        field('First Headscale user', 'headscale_user'),
        jsx(Button, { size: 'sm', disabled: busy || installed || !options.server_url, onClick: () => preview.mutate({ ...options }), children: preview.isPending ? 'Preparing plan…' : 'Preview setup' }),
        error ? jsx(ErrorState, { message: String(error?.message || error) }) : null,
        plan ? jsxs('div', { className: 'flex flex-col gap-2 text-xs', children: [
          jsx('p', { children: 'The installer downloads the verified Headscale package, writes its configuration, starts its service, creates the first user and saves the API key in your active Hermes profile.' }),
          jsx('p', { children: options.tls_mode === 'letsencrypt' ? "Point this domain's DNS at the host and allow inbound TCP 80/443 and UDP 3478. Let's Encrypt receives the domain and contact email." : 'Your existing proxy must forward HTTPS and WebSocket/Upgrade traffic to 127.0.0.1:8080. Allow inbound UDP 3478 for the embedded relay.' }),
          jsxs('details', { children: [
            jsx('summary', { className: 'cursor-pointer', children: 'Review generated configuration' }),
            jsx('pre', { className: 'mt-2 overflow-x-auto whitespace-pre-wrap rounded bg-(--ui-bg-secondary) p-2', children: typeof plan.config === 'string' ? plan.config : JSON.stringify(plan.config, null, 2) })
          ] }),
          jsx(Button, { size: 'sm', disabled: busy, onClick: () => {
            if (window.confirm(`Install Headscale for ${plan.options.server_url} on the host running Hermes? This uses root privileges, creates its system service and saves a new API key in your active profile.`)) {
              install.mutate(plan.options)
            }
          }, children: install.isPending ? 'Installing…' : 'Install and configure' })
        ] }) : null,
        installed ? jsx('p', { className: 'text-sm', children: 'Headscale is installed and configured. Verify that the public HTTPS URL is reachable from a device before joining it.' }) : null
      ] })
    ]
  })
}

function NetPlanePage() {
  const t = usePluginI18n(ID)
  const status = useQuery({ queryKey: ['netplane', 'status'], queryFn: () => ctxRest('/status'), refetchInterval: 15000 })
  const nodes = useQuery({ queryKey: ['netplane', 'nodes'], queryFn: () => ctxRest('/nodes'), refetchInterval: 10000 })
  const preauth = useQuery({ queryKey: ['netplane', 'preauth'], queryFn: () => ctxRest('/preauth'), refetchInterval: 60000 })
  const qc = useQueryClient()
  const mkKey = useMutation({
    mutationFn: () => ctxRest('/preauth', { method: 'POST', body: { expiry_hours: 24, reusable: false } }),
    onSuccess: (r) => {
      haptic('tap')
      host.notify({ kind: 'success', message: `Join key ready: ${r.key.key}` })
      qc.invalidateQueries({ queryKey: ['netplane', 'preauth'] })
    },
    onError: (e) => host.notify({ kind: 'error', message: `preauth failed: ${e?.message || e}` })
  })

  return jsxs('div', {
    className: 'flex h-full flex-col gap-3 overflow-y-auto p-4',
    children: [
      jsxs('div', { className: 'flex items-center justify-between', children: [
        jsxs('div', { className: 'flex items-center gap-2 text-sm font-medium', children: [
          jsx(Codicon, { name: 'globe' }),
          t('pageTitle')
        ] }),
        jsx(Button, { size: 'sm', disabled: mkKey.isPending, onClick: () => mkKey.mutate(), children: t('newKey') })
      ] }),
      status.isError
        ? jsx(ErrorState, { message: String(status.error?.message || status.error) })
        : status.data ? jsx(StatusCard, { status: status.data }) : null,
      jsx(SetupPanel, {}),
      jsxs('div', { className: 'rounded-md border border-(--ui-stroke-secondary)', children: [
        jsx('div', { className: 'px-3 py-1.5 text-xs font-medium text-(--ui-text-secondary) uppercase tracking-wide', children: t('nodes') }),
        ...(nodes.data?.nodes?.length ? nodes.data.nodes.map((n) => jsx(NodeRow, { node: n, n }, n.id)) : [jsx(EmptyState, { key: 'e', message: t('noNodes') })])
      ] }),
      jsxs('div', { className: 'rounded-md border border-(--ui-stroke-secondary)', children: [
        jsx('div', { className: 'px-3 py-1.5 text-xs font-medium text-(--ui-text-secondary) uppercase tracking-wide', children: t('preauth') }),
        ...(preauth.data?.keys?.length ? preauth.data.keys.map((k) => jsx(PreauthRow, { k }, k.id)) : [jsx(EmptyState, { key: 'e', message: t('noKeys') })])
      ] }),
      jsx('div', { className: 'text-xs text-(--ui-text-quaternary)', children: t('joinHint') })
    ]
  })
}

export default {
  id: ID,
  name: 'NetPlane',
  defaultEnabled: false,
  register(ctx) {
    ctxRef = ctx
    ctx.i18n.register({
      en: {
        pageTitle: 'NetPlane — self-hosted tailnet',
        newKey: 'New join key',
        nodes: 'Nodes',
        preauth: 'Preauth keys',
        noNodes: 'No nodes registered yet',
        noKeys: 'No preauth keys',
        joinHint: 'Join a device: tailscale up --login-server=<your control URL> --auth-key=<key>'
      }
    })
    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: '/netplane' },
        render: () => jsx(NetPlanePage, {})
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        data: { path: '/netplane', label: 'NetPlane', codicon: 'globe' }
      },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: {
          id: 'netplane.open',
          label: 'NetPlane: open tailnet dashboard',
          keywords: ['tailscale', 'headscale', 'netplane', 'tailnet'],
          run: () => host.navigate('/netplane')
        }
      }
    ])
  }
}
