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
        <div className="header-actions">
          <span className="header-role">
            {profile?.name ? `Student portal · ${profile.name}` : 'Student portal'}
          </span>
          {onSignOut ? (
            <button type="button" className="header-signout" onClick={onSignOut}>
              Sign out
            </button>
          ) : null}
        </div>
      </div>
    </header>
  )
}
