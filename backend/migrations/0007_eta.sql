-- ETA прибытия посылки на склад-форвардер: извлекается LLM из писем магазинов
-- («Arriving Thursday, August 20»). Ориентир, живёт на подзаказе-посылке;
-- в списках показывается, пока посылка едет к складу (purchased/shipped).
ALTER TABLE suborders ADD COLUMN eta_on DATE;
