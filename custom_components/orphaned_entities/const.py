"""Constants for Orphaned Entities."""

DOMAIN = "orphaned_entities"

CONF_SCAN_INTERVAL = "scan_interval"
CONF_INACTIVITY_DAYS = "inactivity_days"
CONF_IGNORED_DOMAINS = "ignored_domains"

DEFAULT_SCAN_INTERVAL = 24  # hours
DEFAULT_INACTIVITY_DAYS = 30  # days
DEFAULT_IGNORED_DOMAINS = "persistent_notification,group,scene,script,automation,input_boolean,input_number,input_select,input_text,input_datetime,input_button,timer,counter,zone,person,sun,weather,update,device_tracker"

STORAGE_KEY = f"{DOMAIN}.data"
STORAGE_VERSION = 1
