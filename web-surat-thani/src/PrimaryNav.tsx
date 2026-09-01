export type SiteRoute = 'history' | 'current' | 'drone' | 'report' | 'map'

type Props = {
  active: SiteRoute
  onNavigate: (route: SiteRoute) => void
}

const items: Array<{ route: SiteRoute; label: string }> = [
  { route: 'history', label: 'หลักฐานย้อนหลัง' },
  { route: 'current', label: 'ผล 2023–2026' },
  { route: 'drone', label: 'ภาพโดรน HR' },
  { route: 'report', label: 'รายงาน 37-STC' },
  { route: 'map', label: 'แผนที่หลายปี' },
]

export default function PrimaryNav({ active, onNavigate }: Props) {
  return (
    <nav className="primary-nav" aria-label="เมนูหลักสุราษฎร์ธานี 37-STC">
      <div className="primary-nav-brand"><span>สุราษฎร์ธานี</span><strong>37-STC Coastal Evidence</strong></div>
      <div className="primary-nav-links">
        {items.map((item) => (
          <button
            type="button"
            key={item.route}
            className={active === item.route ? 'active' : ''}
            aria-current={active === item.route ? 'page' : undefined}
            onClick={() => onNavigate(item.route)}
          >
            {item.label}
          </button>
        ))}
      </div>
    </nav>
  )
}
