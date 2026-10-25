import { LogoIcon } from './Icons.jsx'

export default function Header() {
  return (
    <header className="site-header">
      <div className="container site-header__inner">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true">
            <LogoIcon />
          </span>
          <span className="brand__name">HostelDesk</span>
        </div>
        <span className="brand__context">Student portal</span>
      </div>
    </header>
  )
}
