import { useEffect, useState } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js";
import { Line } from "react-chartjs-2";
import { apiFetch } from "./api";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

export default function AlertsChart({ token }) {
  const [stats, setStats] = useState([]);
  const [error, setError] = useState(null);

  const loadStats = async () => {
    try {
      const resp = await apiFetch("/api/alerts/stats", {
        headers: { Authorization: `Bearer ${token}` },
        skipReauth: true,
      });
      if (!resp.ok) throw new Error(await resp.text());
      setStats(await resp.json());
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    loadStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) return <p className="error-text">{error}</p>;
  if (stats.length === 0) return <p>No data yet.</p>;

  const labels = stats.map((s) => new Date(s.time).toLocaleTimeString());
  const invalidData = stats.map((s) => s.invalid);
  const blockedData = stats.map((s) => s.blocked);

  const data = {
    labels,
    datasets: [
      {
        label: "Invalid credentials",
        data: invalidData,
        borderColor: "rgb(255, 99, 132)",
        backgroundColor: "rgba(255, 99, 132, 0.5)",
      },
      {
        label: "Blocked Attempts",
        data: blockedData,
        borderColor: "rgba(15, 83, 230, 1)",
        backgroundColor: "rgba(16, 32, 207, 0.6)",
      },
    ],
  };

  const options = {
    responsive: true,
    plugins: {
      legend: {
        position: "top",
      },
    },
  };

  return <Line options={options} data={data} />;
}
