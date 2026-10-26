import { LogoIcon } from './Icons.jsx'

export default function Header({ profile, onSignOut }) {
  return (
    <header className="site-header">
      <div className="container site-header__inner">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true">
            <LogoIcon />
          </span>
          <span className="brand__name">HostelDesk</span>
        </div>
        <span className="brand__context">{profile?.name ? `Student portal · ${profile.name}` : 'Student portal'} {onSignOut && <button type="button" className="student-signout" onClick={onSignOut}>Sign out</button>}</span>
      </div>
    </header>
  )
}
