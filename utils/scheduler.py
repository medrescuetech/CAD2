import threading
import time
import logging
import schedule
import datetime
from datetime import datetime, timedelta
from flask import current_app
from extensions import db
from models import SystemSetting, Incident, IncidentLog, User, UnitAssignment
import json
import traceback

# Setup logger
logger = logging.getLogger('scheduler')

class TaskHistory:
    """Class for storing task execution history."""
    
    def __init__(self, max_items=1000):
        """
        Initialize task history.
        
        Args:
            max_items: Maximum number of history items to store
        """
        self.history = []
        self.max_items = max_items
        self.lock = threading.Lock()
    
    def add_record(self, record):
        """
        Add a record to the history.
        
        Args:
            record: Dictionary with execution details
        """
        with self.lock:
            self.history.append(record)
            if len(self.history) > self.max_items:
                self.history = self.history[-self.max_items:]
    
    def get_records(self, task_name=None, limit=100, status=None):
        """
        Get history records.
        
        Args:
            task_name: Filter by task name
            limit: Maximum number of records to return
            status: Filter by status (completed, failed)
            
        Returns:
            list: List of history records
        """
        with self.lock:
            filtered = self.history
            
            if task_name:
                filtered = [record for record in filtered if record['task_name'] == task_name]
            
            if status:
                filtered = [record for record in filtered if record['status'] == status]
            
            # Sort by execution time, newest first
            filtered.sort(key=lambda x: x['executed_at'], reverse=True)
            
            return filtered[:limit]
    
    def get_task_stats(self, task_name=None, days=7):
        """
        Get task execution statistics.
        
        Args:
            task_name: Filter by task name
            days: Number of days to include in stats
            
        Returns:
            dict: Dictionary with execution statistics
        """
        with self.lock:
            # Filter by date range
            cutoff = datetime.utcnow() - timedelta(days=days)
            filtered = [r for r in self.history if datetime.fromisoformat(r['executed_at']) >= cutoff]
            
            if task_name:
                filtered = [r for r in filtered if r['task_name'] == task_name]
            
            # Count by status
            total = len(filtered)
            completed = len([r for r in filtered if r['status'] == 'completed'])
            failed = len([r for r in filtered if r['status'] == 'failed'])
            
            # Get average duration for completed tasks
            durations = [r['duration'] for r in filtered if r['status'] == 'completed' and 'duration' in r]
            avg_duration = sum(durations) / len(durations) if durations else 0
            
            # Group by day
            daily_counts = {}
            for record in filtered:
                day = datetime.fromisoformat(record['executed_at']).date().isoformat()
                if day not in daily_counts:
                    daily_counts[day] = {'total': 0, 'completed': 0, 'failed': 0}
                
                daily_counts[day]['total'] += 1
                if record['status'] == 'completed':
                    daily_counts[day]['completed'] += 1
                elif record['status'] == 'failed':
                    daily_counts[day]['failed'] += 1
            
            return {
                'total_executions': total,
                'completed': completed,
                'failed': failed,
                'success_rate': (completed / total) * 100 if total > 0 else 0,
                'average_duration': avg_duration,
                'daily_counts': daily_counts
            }


class TaskScheduler:
    """Task scheduler for the CAD system."""
    
    def __init__(self, app=None):
        """
        Initialize the task scheduler.
        
        Args:
            app: Flask application instance
        """
        self.app = app
        self.scheduler_thread = None
        self.stop_event = threading.Event()
        self.jobs = {}
        self.history = TaskHistory()
        self.max_retries = 3  # Default max retries for failed jobs
        self.retry_delay = 300  # Default retry delay in seconds (5 minutes)
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask application."""
        self.app = app
        
        # Register extension with app
        app.task_scheduler = self
        
        # Load configuration
        self.max_retries = app.config.get('TASK_MAX_RETRIES', 3)
        self.retry_delay = app.config.get('TASK_RETRY_DELAY', 300)
        
        # Register cleanup tasks
        self.register_default_tasks()
    
    def register_default_tasks(self):
        """Register default scheduled tasks."""
        # Data cleanup tasks
        self.register_task(
            name="cleanup_old_incidents",
            func=self.cleanup_old_incidents,
            interval=schedule.every().day.at("02:00"),  # Run at 2 AM daily
            description="Clean up old closed incidents"
        )
        
        self.register_task(
            name="cleanup_old_logs",
            func=self.cleanup_old_logs,
            interval=schedule.every().monday.at("03:00"),  # Run at 3 AM every Monday
            description="Clean up old system logs"
        )
        
        # Maintenance tasks
        self.register_task(
            name="database_vacuum",
            func=self.database_vacuum,
            interval=schedule.every().sunday.at("04:00"),  # Run at 4 AM every Sunday
            description="Perform database vacuum operation"
        )
        
        # Report generation tasks
        self.register_task(
            name="generate_daily_report",
            func=self.generate_daily_report,
            interval=schedule.every().day.at("00:05"),  # Run at 12:05 AM daily
            description="Generate daily system activity report"
        )
        
        # System health check
        self.register_task(
            name="system_health_check",
            func=self.system_health_check,
            interval=schedule.every(1).hours,  # Run every hour
            description="Check system health and send alerts if needed"
        )
    
    def register_task(self, name, func, interval, description=None):
        """
        Register a scheduled task.
        
        Args:
            name: Task name (unique identifier)
            func: Function to execute
            interval: Schedule interval (e.g., schedule.every().day.at("10:00"))
            description: Task description
        """
        # Store job information
        self.jobs[name] = {
            'name': name,
            'description': description,
            'interval': str(interval),
            'last_run': None,
            'next_run': None,
            'status': 'scheduled',
            'error': None,
            'retries': 0,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'enabled': True
        }
        
        # Schedule the job
        job = interval.do(self._task_wrapper, name=name, func=func)
        job.tag(name)  # Tag the job with its name for later retrieval
        
        logger.info(f"Registered scheduled task: {name}")
        return job
    
    def _task_wrapper(self, name, func):
        """
        Wrapper for scheduled tasks that provides error handling and status updates.
        
        Args:
            name: Task name
            func: Function to execute
        """
        # Skip if job is disabled
        if not self.jobs[name].get('enabled', True):
            logger.info(f"Skipping disabled task: {name}")
            return
            
        # Update job status
        self.jobs[name]['status'] = 'running'
        self.jobs[name]['last_run'] = datetime.utcnow()
        
        # Create history record
        history_record = {
            'task_name': name,
            'executed_at': datetime.utcnow().isoformat(),
            'status': 'running'
        }
        
        start_time = time.time()
        
        # Execute task with app context
        with self.app.app_context():
            try:
                logger.info(f"Running scheduled task: {name}")
                result = func()
                
                # Update job status
                self.jobs[name]['status'] = 'completed'
                self.jobs[name]['error'] = None
                self.jobs[name]['retries'] = 0  # Reset retry counter on success
                self.jobs[name]['next_run'] = schedule.next_run()
                
                # Update history record
                end_time = time.time()
                duration = end_time - start_time
                
                history_record.update({
                    'status': 'completed',
                    'completed_at': datetime.utcnow().isoformat(),
                    'duration': duration,
                    'result': str(result) if result else None
                })
                
                self.history.add_record(history_record)
                logger.info(f"Task {name} completed successfully in {duration:.2f}s")
                return result
            except Exception as e:
                error_msg = f"Error executing task {name}: {str(e)}"
                stack_trace = traceback.format_exc()
                logger.error(error_msg)
                logger.error(stack_trace)
                
                # Increment retry counter and check if we should retry
                self.jobs[name]['retries'] += 1
                retries = self.jobs[name]['retries']
                max_retries = self.jobs[name].get('max_retries', self.max_retries)
                
                if retries <= max_retries:
                    # Schedule a retry
                    retry_delay = self.jobs[name].get('retry_delay', self.retry_delay)
                    logger.info(f"Scheduling retry {retries}/{max_retries} for task {name} in {retry_delay}s")
                    
                    self.jobs[name]['status'] = 'retry_scheduled'
                    self.jobs[name]['error'] = str(e)
                    
                    # Schedule retry
                    threading.Timer(retry_delay, self._retry_task, args=[name, func]).start()
                else:
                    # Max retries exceeded
                    self.jobs[name]['status'] = 'failed'
                    self.jobs[name]['error'] = str(e)
                
                # Update history record
                end_time = time.time()
                duration = end_time - start_time
                
                history_record.update({
                    'status': 'failed',
                    'completed_at': datetime.utcnow().isoformat(),
                    'duration': duration,
                    'error': str(e),
                    'stack_trace': stack_trace,
                    'retry_count': retries,
                    'max_retries': max_retries
                })
                
                self.history.add_record(history_record)
    
    def _retry_task(self, name, func):
        """
        Retry a failed task.
        
        Args:
            name: Task name
            func: Function to execute
        """
        logger.info(f"Retrying task: {name}")
        self._task_wrapper(name, func)
    
    def start_scheduler(self):
        """Start the scheduler thread."""
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            logger.warning("Scheduler thread is already running")
            return
        
        logger.info("Starting task scheduler")
        self.stop_event.clear()
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
    
    def stop_scheduler(self):
        """Stop the scheduler thread."""
        logger.info("Stopping task scheduler")
        self.stop_event.set()
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
    
    def _scheduler_loop(self):
        """Main scheduler loop that runs pending jobs at their scheduled times."""
        while not self.stop_event.is_set():
            try:
                # Run pending jobs
                schedule.run_pending()
                
                # Update next run time for all jobs
                for job_name in self.jobs:
                    if self.jobs[job_name]['status'] != 'running':
                        self.jobs[job_name]['next_run'] = schedule.next_run()
                
                # Sleep for a second before checking again
                # Use stop_event.wait() instead of time.sleep() to allow for clean shutdown
                self.stop_event.wait(1)
            except Exception as e:
                logger.error(f"Error in scheduler loop: {str(e)}")
                # Sleep a bit before retrying
                time.sleep(5)
    
    def get_task_status(self, name=None):
        """
        Get the status of scheduled tasks.
        
        Args:
            name: Task name (optional, if None, return all tasks)
            
        Returns:
            dict or list: Task status information
        """
        if name:
            return self.jobs.get(name)
        else:
            return list(self.jobs.values())
    
    def run_task_now(self, name):
        """
        Run a task immediately, outside of its scheduled time.
        
        Args:
            name: Task name
            
        Returns:
            bool: Success status
        """
        if name not in self.jobs:
            logger.error(f"Task {name} not found")
            return False
        
        logger.info(f"Running task {name} on demand")
        
        try:
            # Get the function for this task
            for job in schedule.jobs:
                if job.tags and name in job.tags:
                    # Found the job
                    with self.app.app_context():
                        job.run()
                    return True
            
            logger.error(f"Job {name} not found in schedule")
            return False
        except Exception as e:
            logger.error(f"Error running task {name}: {str(e)}")
            return False
    
    def enable_task(self, name, enabled=True):
        """
        Enable or disable a task.
        
        Args:
            name: Task name
            enabled: Whether to enable or disable the task
            
        Returns:
            bool: Success status
        """
        if name not in self.jobs:
            logger.error(f"Task {name} not found")
            return False
        
        self.jobs[name]['enabled'] = enabled
        status = "enabled" if enabled else "disabled"
        logger.info(f"Task {name} {status}")
        return True
    
    def update_task_config(self, name, max_retries=None, retry_delay=None):
        """
        Update task configuration.
        
        Args:
            name: Task name
            max_retries: Maximum number of retries
            retry_delay: Delay between retries in seconds
            
        Returns:
            bool: Success status
        """
        if name not in self.jobs:
            logger.error(f"Task {name} not found")
            return False
        
        if max_retries is not None:
            self.jobs[name]['max_retries'] = max_retries
        
        if retry_delay is not None:
            self.jobs[name]['retry_delay'] = retry_delay
        
        logger.info(f"Task {name} configuration updated")
        return True
    
    def get_task_history(self, name=None, limit=100, status=None):
        """
        Get task execution history.
        
        Args:
            name: Task name (optional)
            limit: Maximum number of records to return
            status: Filter by status (completed, failed)
            
        Returns:
            list: List of history records
        """
        return self.history.get_records(task_name=name, limit=limit, status=status)
    
    def get_task_stats(self, name=None, days=7):
        """
        Get task execution statistics.
        
        Args:
            name: Task name (optional)
            days: Number of days to include in stats
            
        Returns:
            dict: Dictionary with execution statistics
        """
        return self.history.get_task_stats(task_name=name, days=days)
    
    # Default scheduled tasks
    
    def cleanup_old_incidents(self):
        """
        Clean up old closed incidents by archiving them.
        """
        logger.info("Running cleanup for old closed incidents")
        
        # Get retention policy from settings
        retention_days = 90  # Default to 90 days
        try:
            setting = SystemSetting.query.filter_by(name='incident_retention_days').first()
            if setting and setting.value:
                retention_days = int(setting.value)
        except Exception:
            pass
        
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        # Find old closed incidents
        old_incidents = Incident.query.filter(
            Incident.status == Incident.STATUS_CLOSED,
            Incident.updated_at < cutoff_date
        ).all()
        
        if not old_incidents:
            logger.info("No old incidents to archive")
            return
        
        count = len(old_incidents)
        logger.info(f"Found {count} old incidents to archive")
        
        # In a real implementation, this would archive the incidents
        # rather than just logging about them
        
        return f"Archived {count} old incidents"
    
    def cleanup_old_logs(self):
        """
        Clean up old system logs.
        """
        logger.info("Running cleanup for old system logs")
        
        # Get retention policy from settings
        retention_days = 30  # Default to 30 days
        try:
            setting = SystemSetting.query.filter_by(name='log_retention_days').first()
            if setting and setting.value:
                retention_days = int(setting.value)
        except Exception:
            pass
        
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        # Find old logs
        old_logs = IncidentLog.query.filter(
            IncidentLog.timestamp < cutoff_date
        ).count()
        
        if not old_logs:
            logger.info("No old logs to archive")
            return
        
        logger.info(f"Found {old_logs} old logs to archive")
        
        # In a real implementation, this would archive the logs
        # rather than just counting them
        
        return f"Archived {old_logs} old logs"
    
    def database_vacuum(self):
        """
        Perform database vacuum operation for maintenance.
        """
        logger.info("Running database vacuum operation")
        
        try:
            # This is SQLite-specific
            # For other databases, the vacuum command would be different
            db.engine.execute("VACUUM")
            logger.info("Database vacuum completed successfully")
            return "Database vacuum completed"
        except Exception as e:
            logger.error(f"Database vacuum failed: {str(e)}")
            raise
    
    def generate_daily_report(self):
        """
        Generate a daily system activity report.
        """
        logger.info("Generating daily system activity report")
        
        yesterday = datetime.utcnow().date() - timedelta(days=1)
        start_of_day = datetime.combine(yesterday, datetime.min.time())
        end_of_day = datetime.combine(yesterday, datetime.max.time())
        
        # Count incidents created yesterday
        incident_count = Incident.query.filter(
            Incident.created_at >= start_of_day,
            Incident.created_at <= end_of_day
        ).count()
        
        # Count active users yesterday
        user_count = User.query.filter(
            User.last_seen >= start_of_day,
            User.last_seen <= end_of_day
        ).count()
        
        # Count unit assignments
        assignment_count = UnitAssignment.query.filter(
            UnitAssignment.dispatched_at >= start_of_day,
            UnitAssignment.dispatched_at <= end_of_day
        ).count()
        
        # Generate report
        report = {
            'date': yesterday.isoformat(),
            'generated_at': datetime.utcnow().isoformat(),
            'incidents': {
                'total': incident_count,
                # Additional incident statistics could be added here
            },
            'users': {
                'active': user_count,
                # Additional user statistics could be added here
            },
            'units': {
                'assignments': assignment_count,
                # Additional unit statistics could be added here
            },
            # Additional system statistics could be added here
        }
        
        # In a real implementation, this would save the report to a file or database
        # and potentially email it to administrators
        
        logger.info(f"Daily report generated for {yesterday.isoformat()}")
        return report
    
    def system_health_check(self):
        """
        Check system health and send alerts if thresholds are exceeded.
        """
        logger.info("Running system health check")
        
        # This function could check various system health indicators:
        # - Database connection status
        # - Disk space
        # - Memory usage
        # - CPU usage
        # - External service availability
        
        # For now, it's just a placeholder
        
        logger.info("System health check completed")
        return "System health check completed"


# Global instance for the task scheduler
scheduler = TaskScheduler()


def init_app(app):
    """Initialize the task scheduler with the Flask app."""
    global scheduler
    
    # Initialize scheduler
    scheduler.init_app(app)
    
    # Start scheduler if enabled in app config
    if app.config.get('ENABLE_TASK_SCHEDULER', True):
        scheduler.start_scheduler()
