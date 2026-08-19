import { NavLink, Link } from "react-router-dom";
import { Library, BookOpen, FileUp, SlidersHorizontal, PanelLeftClose, PanelLeftOpen, LogOut, User, Sun, Moon, Images } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { useAuth } from "@/auth";
import { useTheme } from "@/theme";

const navItems = [
  { to: "/", icon: Library, label: "Library" },
  { to: "/gallery", icon: Images, label: "Gallery" },
  { to: "/import", icon: FileUp, label: "Import" },
  { to: "/codex", icon: BookOpen, label: "Codex" },
  { to: "/settings", icon: SlidersHorizontal, label: "Settings" },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const { user, authMode, logout } = useAuth();
  const { mode, toggleMode } = useTheme();
  const [showMenu, setShowMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    }
    if (showMenu) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showMenu]);

  return (
    <aside
      className={`bg-tc-page border-r border-tc-default flex flex-col flex-shrink-0 transition-[width] duration-200 ${
        collapsed ? "w-14" : "w-56"
      }`}
    >
      <div className="p-4 border-b border-tc-default flex items-center justify-between min-h-[57px]">
        {!collapsed && (
          <Link to="/" className="text-xl font-bold tracking-tight text-tc-primary hover:text-tc-primary transition-colors">
            Typecast
          </Link>
        )}
        <button
          onClick={onToggle}
          className={`p-1 text-tc-muted hover:text-tc-secondary rounded transition-colors ${collapsed ? "mx-auto" : ""}`}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>
      <nav className="flex-1 p-2 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg text-sm font-medium transition-colors ${
                collapsed ? "justify-center px-2 py-2" : "px-3 py-2"
              } ${
                isActive
                  ? "bg-tc-overlay text-tc-primary"
                  : "text-tc-tertiary hover:text-tc-secondary hover:bg-tc-overlay/50"
              }`
            }
          >
            <Icon size={18} />
            {!collapsed && label}
          </NavLink>
        ))}
      </nav>

      {user && (
        <div className="relative p-2 border-t border-tc-default" ref={menuRef}>
          <button
            onClick={() => setShowMenu(!showMenu)}
            className={`flex items-center gap-2 w-full rounded-lg text-sm text-tc-tertiary hover:text-tc-secondary hover:bg-tc-overlay/50 transition-colors ${
              collapsed ? "justify-center px-2 py-2" : "px-3 py-2"
            }`}
            title={collapsed ? user.display_name : undefined}
          >
            {user.avatar_url ? (
              <img src={user.avatar_url} alt="" className="w-5 h-5 rounded-full object-cover" />
            ) : (
              <User size={18} />
            )}
            {!collapsed && (
              <span className="truncate text-xs">{user.display_name}</span>
            )}
          </button>
          {showMenu && (
            <div className="absolute bottom-full left-2 mb-1 w-48 bg-tc-overlay border border-tc-subtle rounded-lg shadow-xl py-1 z-50">
              <div className="px-3 py-2 border-b border-tc-subtle">
                <p className="text-xs font-medium text-tc-primary truncate">{user.display_name}</p>
                <p className="text-[10px] text-tc-muted truncate">{user.email}</p>
              </div>
              <button
                onClick={toggleMode}
                className="flex items-center gap-2 px-3 py-2 w-full text-left text-xs text-tc-tertiary hover:text-tc-secondary hover:bg-tc-hover transition-colors"
              >
                {mode === "dark" ? <Sun size={12} /> : <Moon size={12} />}
                {mode === "dark" ? "Light mode" : "Dark mode"}
              </button>
              {authMode !== "local" && (
                <button
                  onClick={() => { logout(); setShowMenu(false); }}
                  className="flex items-center gap-2 px-3 py-2 w-full text-left text-xs text-tc-tertiary hover:text-tc-secondary hover:bg-tc-hover transition-colors"
                >
                  <LogOut size={12} />
                  Sign out
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </aside>
  );
}
