import React, { useState } from 'react';
import AlertsChart from '../AlertsChart';
import AlertsTable from '../AlertsTable';
import AuthEventsTable from '../AuthEventsTable';
import LoginForm from '../LoginForm';
import LoginStatus from '../LoginStatus';
import SecurityToggle from '../SecurityToggle';
import AttackSim from '../AttackSim';
import CredentialStuffingChart from '../credentialStuffingChart';
import { AUTH_TOKEN_KEY } from '../api';

const Dashboard = () => {
  const [token, setToken] = useState(localStorage.getItem(AUTH_TOKEN_KEY));

  const handleLogin = (newToken) => setToken(newToken);

  return (
    <div className="p-6 bg-gray-100 min-h-screen">
      <h1 className="text-3xl font-bold mb-6">API Security Dashboard</h1>

      {!token && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <LoginForm onLogin={handleLogin} />
        </div>
      )}

      {token && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
            <LoginStatus token={token} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
            <div className="lg:col-span-2"><AlertsChart /></div>
            <div className="lg:col-span-1"><SecurityToggle /><AttackSim /></div>
          </div>

          <div className="mb-6"><CredentialStuffingChart /></div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <AlertsTable />
            <AuthEventsTable />
          </div>
        </>
      )}
    </div>
  );
};

export default Dashboard;