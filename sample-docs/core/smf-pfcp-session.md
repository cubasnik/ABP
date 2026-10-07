---
title: SMF и UPF: установление сессии по PFCP
product: Packet Core 5G
vendor: Ericsson
domain: Core
release: 24.Q3
node_type: SMF
interface: N4
protocol: PFCP
topic: Сессии
---
# SMF и UPF: установление сессии по PFCP

## Роль интерфейса N4
Интерфейс N4 связывает функцию управления сессиями SMF с функцией пользовательской плоскости UPF. Управление идёт по протоколу PFCP поверх UDP, порт 8805. SMF создаёт правила обнаружения пакетов PDR, правила пересылки FAR и правила QoS QER, а UPF применяет их к трафику абонента.

## Сообщения установления сессии
Сессия создаётся сообщением PFCP Session Establishment Request от SMF. UPF отвечает Session Establishment Response с причиной Request accepted и выделенным F-SEID. Изменение правил выполняется парой Session Modification Request и Response, удаление — Session Deletion Request.

## Ассоциация узлов
До первой сессии SMF и UPF обмениваются PFCP Association Setup Request и Response. Если ассоциация отсутствует, UPF отвергает установление сессии с причиной No established PFCP association. Проверить ассоциацию можно командой show pfcp association на SMF.

## Диагностика отказов
Причина Mandatory IE missing означает, что в запросе нет обязательного элемента, обычно это ошибка версии ПО между SMF и UPF. Причина Request rejected без деталей часто связана с исчерпанием пула адресов UE на UPF. Причина Session context not found при модификации говорит о том, что UPF уже удалил сессию по таймеру неактивности.

## Таймеры и повторные передачи
Параметр pfcpRetransmissionTimer задаёт интервал повторной отправки запроса, по умолчанию 3 секунды, параметр pfcpMaxRetries ограничивает число повторов, по умолчанию 3. Heartbeat Request отправляется каждые 60 секунд; три пропущенных ответа подряд переводят ассоциацию в состояние DOWN.
