import React, { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { apiFetch } from './api';

const CredentialStuffingChart = () => {
  const [data, setData] = useState([]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const resp = await apiFetch('/api/credential-stuffing-stats');
        if (!resp.ok) throw new Error('stats fetch failed');
        const stats = await resp.json();
        const chartData = [
          { name: 'Alice', total: stats.alice?.total_attempts || 0, successful: stats.alice?.successful_attempts || 0 },
          { name: 'Ben',   total: stats.ben?.total_attempts || 0,   successful: stats.ben?.successful_attempts || 0 },
        ];
        setData(chartData);
      } catch (error) {
        console.error('Error fetching credential stuffing stats:', error);
        setData([]);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="bg-white p-4 rounded-lg shadow">
      <h2 className="text-xl font-semibold mb-4">Credential Stuffing Attempts</h2>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" />
          <YAxis />
          <Tooltip />
          <Legend />
          <Bar dataKey="total" name="Total Attempts" />
          <Bar dataKey="successful" name="Successful Attempts" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default CredentialStuffingChart;