import pytest
from src.checker import check_availability

def test_check_availability(mocker):
    mocker.patch('src.checker.send_notification')
    mocker.patch('src.checker.driver')
    
    # Simulate available hours
    mocker.patch('src.checker.driver.find_elements', return_value=['slot1', 'slot2'])
    
    result = check_availability()
    
    assert result == "Available hours found: 2 slots."
    assert check_availability.send_notification.called

def test_no_available_hours(mocker):
    mocker.patch('src.checker.send_notification')
    mocker.patch('src.checker.driver')
    
    # Simulate no available hours
    mocker.patch('src.checker.driver.find_elements', return_value=[])
    
    result = check_availability()
    
    assert result == "No available hours."
    assert not check_availability.send_notification.called