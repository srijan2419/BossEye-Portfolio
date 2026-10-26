import {
  Paper,
  Typography,
  Grid,
  Box,
  IconButton,
  alpha,
  useTheme,
} from '@mui/material';
import { InfoOutlined } from '@mui/icons-material';

interface ActivityData {
  id: number;
  zone_uuid: string;
  camera_uuid: string;
  zone_track_id: number;
  activity_type: string;
  confidence: number;
  timestamp: string;
  is_primary: boolean;
  image_path: string;
}

interface Activity {
  activity: string;
  count: number;
  array?: ActivityData[];
}

interface Camera {
  name: string;
  camera_uuid: string;
  location: string;
  activities: Activity[];
  camera_total_activities: number;
}

interface DayData {
  date: string;
  camera: Camera[];
  day_total_activities: number;
}

interface EventLogTableProps {
  data: DayData[];
  getEventTypeColor: (type: string) => string;
  fetchDetailedData: (date: string, cameraUuid?: string, activityType?: string) => Promise<ActivityData[]>;
  setSelectedDay: (day: DayData) => void;
  setDialogSelectedCamera: (uuid: string) => void;
  setDialogSelectedActivity: (activity: string) => void;
  setIsDialogOpen: (open: boolean) => void;
}

const EventLogTable = ({
  data,
  getEventTypeColor,
  fetchDetailedData,
  setSelectedDay,
  setDialogSelectedCamera,
  setDialogSelectedActivity,
  setIsDialogOpen,
}: EventLogTableProps) => {
  const theme = useTheme();

  const handleInfoClick = async (dayData: DayData, camera: Camera, activity: Activity) => {
    setSelectedDay(dayData);
    setDialogSelectedCamera(camera.camera_uuid);
    setDialogSelectedActivity(activity.activity);
    setIsDialogOpen(true);

    // Progressive loading: Fetch detailed data for this specific day/camera/activity
    const detailedActivities = await fetchDetailedData(
      dayData.date,
      camera.camera_uuid,
      activity.activity
    );

    if (detailedActivities.length > 0) {
      const activitiesLookup = new Map<string, ActivityData[]>();

      detailedActivities.forEach((item: ActivityData) => {
        const key = `${item.camera_uuid}:${item.activity_type}`;
        if (!activitiesLookup.has(key)) {
          activitiesLookup.set(key, []);
        }
        activitiesLookup.get(key)!.push(item);
      });

      const updatedDayData = { ...dayData };
      updatedDayData.camera.forEach((cam) => {
        cam.activities.forEach((act) => {
          const key = `${cam.camera_uuid}:${act.activity}`;
          const matchingActivities = activitiesLookup.get(key) || [];
          if (matchingActivities.length > 0) {
            act.array = matchingActivities;
          }
        });
      });

      setSelectedDay(updatedDayData);
    }
  };

  return (
    <Grid item xs={12}>
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
        Activity Event Log
      </Typography>
      <Paper sx={{ p: 2, overflowX: 'auto' }}>
        <Box sx={{ minWidth: 800 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e0e0e0' }}>
                <th style={{ padding: '12px 16px', textAlign: 'left' }}>Date</th>
                <th style={{ padding: '12px 16px', textAlign: 'left' }}>Camera</th>
                <th style={{ padding: '12px 16px', textAlign: 'left' }}>Location</th>
                <th style={{ padding: '12px 16px', textAlign: 'left' }}>Activity</th>
                <th style={{ padding: '12px 16px', textAlign: 'right' }}>Count</th>
                <th style={{ padding: '12px 16px', textAlign: 'center' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.map((dayData: DayData) =>
                dayData.camera.map((camera: Camera) =>
                  camera.activities.map((activity: Activity, actIndex: number) => (
                    <tr
                      key={`${dayData.date}-${camera.camera_uuid}-${actIndex}`}
                      style={{
                        borderBottom: '1px solid #e0e0e0',
                        backgroundColor:
                          actIndex % 2 === 0
                            ? alpha(theme.palette.background.paper, 0.5)
                            : theme.palette.background.paper,
                      }}
                    >
                      <td style={{ padding: '12px 16px' }}>{dayData.date}</td>
                      <td style={{ padding: '12px 16px' }}>{camera.name}</td>
                      <td style={{ padding: '12px 16px' }}>{camera.location}</td>
                      <td style={{ padding: '12px 16px' }}>
                        <Box
                          component="span"
                          sx={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 1,
                            color: getEventTypeColor(activity.activity),
                            fontWeight: 500,
                          }}
                        >
                          {activity.activity}
                        </Box>
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'right' }}>{activity.count}</td>
                      <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                        <IconButton
                          size="small"
                          onClick={() => handleInfoClick(dayData, camera, activity)}
                          sx={{
                            color: 'primary.main',
                            '&:hover': {
                              backgroundColor: alpha(theme.palette.primary.main, 0.1),
                            },
                          }}
                        >
                          <InfoOutlined />
                        </IconButton>
                      </td>
                    </tr>
                  ))
                )
              )}
            </tbody>
          </table>
        </Box>
      </Paper>
    </Grid>
  );
};

export default EventLogTable;
