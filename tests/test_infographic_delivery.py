from unittest.mock import MagicMock

from src.notification import NotificationService, NotificationChannel


def test_telegram_image_does_not_also_send_text():
    notifier = NotificationService.__new__(NotificationService)
    notifier._should_use_image_for_channel = MagicMock(return_value=True)
    notifier._send_telegram_photo = MagicMock(return_value=True)
    notifier.send_to_telegram = MagicMock(return_value=True)
    assert notifier._send_to_static_channel(
        NotificationChannel.TELEGRAM, '完整原文', image_bytes=b'png',
        email_stock_codes=None, email_send_to_all=False,
    )
    notifier._send_telegram_photo.assert_called_once_with(b'png')
    notifier.send_to_telegram.assert_not_called()


def test_telegram_unavailable_image_keeps_text_fallback():
    notifier = NotificationService.__new__(NotificationService)
    notifier._should_use_image_for_channel = MagicMock(return_value=False)
    notifier._send_telegram_photo = MagicMock()
    notifier.send_to_telegram = MagicMock(return_value=True)
    assert notifier._send_to_static_channel(
        NotificationChannel.TELEGRAM, '完整原文', image_bytes=None,
        email_stock_codes=None, email_send_to_all=False,
    )
    notifier.send_to_telegram.assert_called_once_with('完整原文')
    notifier._send_telegram_photo.assert_not_called()


def test_email_image_receives_full_report():
    notifier = NotificationService.__new__(NotificationService)
    notifier._stock_email_groups = []
    notifier._should_use_image_for_channel = MagicMock(return_value=True)
    notifier._send_email_with_inline_image = MagicMock(return_value=True)
    notifier.send_to_email = MagicMock()
    assert notifier._send_to_static_channel(
        NotificationChannel.EMAIL, '[dsa-market-region]: # (tw)\n\n完整原文',
        image_bytes=b'png', email_stock_codes=None, email_send_to_all=False,
    )
    notifier._send_email_with_inline_image.assert_called_once_with(
        b'png', receivers=None, content='完整原文',
    )
    notifier.send_to_email.assert_not_called()
