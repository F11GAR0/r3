import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth, isPM, isAdmin } from "./auth";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Workbench from "./pages/Workbench";
import Wizard from "./pages/Wizard";
import Settings from "./pages/Settings";
import Stats from "./pages/Stats";
import PmBacklog from "./pages/PmBacklog";
import Profile from "./pages/Profile";
import Layout from "./components/Layout";

/**
 * Top-level route table with role gating.
 */
function App() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-500">
        Загрузка…
      </div>
    );
  }
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route element={user ? <Layout /> : <Navigate to="/login" replace />}>
        <Route path="/" element={<Home />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/workbench" element={<Workbench />} />
        <Route path="/wizard" element={<Wizard />} />
        <Route path="/stats" element={isPM(user) ? <Stats /> : <Navigate to="/" replace />} />
        <Route
          path="/backlog"
          element={isPM(user) ? <PmBacklog /> : <Navigate to="/" replace />}
        />
        <Route
          path="/settings"
          element={isAdmin(user) ? <Settings /> : <Navigate to="/" replace />}
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
