import {
  Paper,
  Typography,
  Grid,
  useTheme,
} from '@mui/material';
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from 'recharts';

interface DistributionEntry {
  name: string;
  value: number;
  color: string;
}

interface EventDistributionChartProps {
  eventDistribution: DistributionEntry[];
  cameraActivity: DistributionEntry[];
}

const EventDistributionChart = ({
  eventDistribution,
  cameraActivity,
}: EventDistributionChartProps) => {
  const theme = useTheme();

  const darkTooltipPaperSx = {
    p: 2.5,
    bgcolor: '#1a1a1a',
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.8), 0 0 0 1px rgba(255, 255, 255, 0.1)',
    border: '1px solid rgba(255, 255, 255, 0.2)',
    borderRadius: 3,
    position: 'relative' as const,
    zIndex: 9999,
    '&::before': {
      content: '""',
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      bgcolor: '#1a1a1a',
      borderRadius: 3,
      zIndex: -1,
    },
  };

  return (
    <>
      <Grid item xs={12} md={6}>
        <Typography
          variant="h6"
          component="div"
          gutterBottom
          sx={{
            fontFamily: 'Inter, sans-serif',
            fontWeight: 800,
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
          }}
        >
          Event Distribution
        </Typography>
        <Paper sx={{ p: 2, height: 400 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={eventDistribution}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                fill="#8884d8"
                paddingAngle={5}
                dataKey="value"
                label
              >
                {eventDistribution.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <RechartsTooltip
                content={({ active, payload }) => {
                  if (active && payload && payload.length) {
                    return (
                      <Paper sx={darkTooltipPaperSx}>
                        <Typography
                          variant="body2"
                          sx={{ color: '#ffffff', fontWeight: 700, textShadow: '0 1px 2px rgba(0, 0, 0, 0.8)' }}
                        >
                          {payload[0].name}: {payload[0].value} events
                        </Typography>
                      </Paper>
                    );
                  }
                  return null;
                }}
              />
              <Legend
                formatter={(value) => (
                  <span style={{ color: theme.palette.text.primary }}>{value}</span>
                )}
              />
            </PieChart>
          </ResponsiveContainer>
        </Paper>
      </Grid>

      <Grid item xs={12} md={6}>
        <Typography
          variant="h6"
          component="div"
          gutterBottom
          sx={{
            fontFamily: 'Inter, sans-serif',
            fontWeight: 800,
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
          }}
        >
          Camera Activity
        </Typography>
        <Paper sx={{ p: 2, height: 400 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={cameraActivity || []} barSize={30}>
              <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
              <XAxis
                dataKey="name"
                angle={-45}
                textAnchor="end"
                height={60}
                interval={0}
                tick={{ fontSize: 12, fill: theme.palette.text.primary }}
                stroke={theme.palette.text.primary}
              />
              <YAxis
                tick={{ fill: theme.palette.text.primary }}
                stroke={theme.palette.text.primary}
              />
              <RechartsTooltip
                content={({ active, payload, label }) => {
                  if (active && payload && payload.length) {
                    return (
                      <Paper sx={darkTooltipPaperSx}>
                        <Typography
                          variant="body2"
                          sx={{ color: '#ffffff', fontWeight: 700, textShadow: '0 1px 2px rgba(0, 0, 0, 0.8)' }}
                        >
                          {label}
                        </Typography>
                        <Typography
                          variant="body2"
                          sx={{ color: '#ffffff', fontWeight: 600, textShadow: '0 1px 2px rgba(0, 0, 0, 0.8)', mt: 0.5 }}
                        >
                          Count: {payload[0].value}
                        </Typography>
                      </Paper>
                    );
                  }
                  return null;
                }}
              />
              <Legend
                formatter={(value) => (
                  <span style={{ color: theme.palette.text.primary }}>{value}</span>
                )}
              />
              <Bar dataKey="value" name="Events" radius={[4, 4, 0, 0]}>
                {(cameraActivity || []).map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Paper>
      </Grid>
    </>
  );
};

export default EventDistributionChart;
