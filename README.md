# no need to modify the code
just call the service to fire event!
 ```yaml
 event_type: xiaomi_aqara.click
 event_data:
      entity_id: binary_sensor.switch_158d000xxxxxc2
      click_type: single
```

# unicode SMS
notify.py (under /usr/src/homeassistant/homeassistant/components/sms/ directory) modified to support unicode SMS (ex. Chinese).
