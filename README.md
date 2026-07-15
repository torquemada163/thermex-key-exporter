# Thermex Key Exporter

Неофициальная desktop-утилита для экспорта локальных ключей Wi-Fi-устройств
Thermex из Thermex Home. Полученные `device_id` и `local_key` подходят для
ручного добавления устройств в LocalTuya для Home Assistant.

## Установка

### Что скачивать

Для обычного использования скачайте готовый архив для своей операционной
системы из раздела **Releases** этого репозитория и распакуйте его целиком.
Это конечный пользовательский архив.

Artifact из вкладки **Actions** с суффиксом `-release-profile` — только
транспортная упаковка CI. Внутри неё находятся конечный архив для Release и
`SHA256SUMS.txt`; такой внешний ZIP не нужно передавать пользователям.

### Что находится в пользовательском архиве

В каждом пользовательском архиве находятся две самостоятельные версии
приложения: GUI, рекомендуемый для большинства людей, и CLI для терминала.

| Платформа | GUI | CLI |
| --- | --- | --- |
| Windows x64 | `ThermexKeyExporter\ThermexKeyExporter.exe` | `thermex-key-exporter\thermex-key-exporter.exe` |
| macOS ARM64 | `ThermexKeyExporter.app` | `ThermexKeyExporterCLI.app/Contents/MacOS/thermex-key-exporter` |
| Linux x64 | `ThermexKeyExporter/ThermexKeyExporter` | `thermex-key-exporter/thermex-key-exporter` |

На Windows и Linux не переносите отдельно исполняемый файл: рядом с ним должна
остаться его папка `_internal` со всеми библиотеками и встроенным профилем. На
macOS не изменяйте содержимое обоих `.app`-bundle и не выносите из них
исполняемые файлы.

Для работы нужны:

- компьютер с доступом в интернет;
- Thermex Home на телефоне с уже добавленными устройствами.

APK, Python, ADB, Java, кабель телефона и доступ к роутеру не нужны.

## Экспорт ключей

1. Запустите GUI-приложение из таблицы выше либо CLI из его папки.
2. Для CLI выполните одну из команд:

   ```text
   Windows: .\thermex-key-exporter.exe export --output thermex-localtuya.json
   Linux: ./thermex-key-exporter export --output thermex-localtuya.json
   macOS: ./ThermexKeyExporterCLI.app/Contents/MacOS/thermex-key-exporter export --output thermex-localtuya.json
   ```

3. Отсканируйте открывшийся QR-код в Thermex Home и подтвердите вход.
4. После завершения откройте созданный JSON-файл.

В JSON у каждого устройства есть `device_id` и `local_key`. Не публикуйте этот
файл и не передавайте его содержимое в issue, логах или чатах. Рядом создаётся
текстовый отчёт, в котором ключи замаскированы.

### Первый запуск на macOS

Сборки для macOS не заверены Apple Developer ID и могут потребовать одноразового
подтверждения в системном диалоге. Для GUI откройте `ThermexKeyExporter.app`.
Для CLI один раз подтвердите открытие `ThermexKeyExporterCLI.app` через Finder,
а затем запускайте указанную выше команду из Terminal. Не отключайте Gatekeeper
и не снимайте карантин с отдельных файлов внутри `.app`.

## Важно

- Утилита не запрашивает пароль Thermex Home.
- Она не отправляет команды устройствам и не меняет настройки сети или роутера.
- Локальный IP не определяется автоматически. Для LocalTuya укажите известный
  IP устройства вручную.
- Если утилита сообщает об устаревшем профиле, установите более новую версию
  из Releases.

## Поддержка

При создании issue укажите версию утилиты, операционную систему и текст ошибки.
Не прикладывайте APK, JSON-экспорт, local keys, QR-коды, токены или данные
учётной записи.

## Лицензия

Проект распространяется под лицензией MIT. Это неофициальная утилита, не
являющаяся продуктом Thermex, Tuya или Home Assistant.
