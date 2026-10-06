-- Base de conhecimento inicial. Preços = estimativa de mercado (assistência independente, SP, 2026),
-- validado = false até o dono da loja conferir. A IA sempre fala em "faixa" e "confirmamos na avaliação".

insert into senhor_smart_at.loja_info (chave, valor, confirmado) values
  ('nome_loja', 'Senhor Smart', true),
  ('nome_ia', 'Sofia', true),
  ('endereco', 'Av. João Firmino, 330, Loja 03, Assunção, São Bernardo do Campo (dentro do Posto Shell)', true),
  ('horario_texto', 'segunda a sexta das 8h30 às 18h30, sábado das 8h30 às 16h30', true),
  ('garantia_servico', '90 dias de garantia no serviço', true),
  ('diagnostico', 'avaliação na loja sem compromisso', false),
  ('formas_pagamento', 'Pix, débito e cartão de crédito', false),
  ('prazo_padrao', 'a maioria dos reparos fica pronta no mesmo dia ou em até 48h, dependendo da peça', false),
  ('leva_e_traz', 'não', false),
  ('venda_aparelhos', 'também vendemos celulares Android no boleto parcelado, com entrada a partir de R$ 240', true);

insert into senhor_smart_at.horario_funcionamento values
  (0, null, null, true),
  (1, '08:30', '18:30', false), (2, '08:30', '18:30', false), (3, '08:30', '18:30', false),
  (4, '08:30', '18:30', false), (5, '08:30', '18:30', false),
  (6, '08:30', '16:30', false);

insert into senhor_smart_at.feriados values
  ('2026-10-12', 'Nossa Senhora Aparecida'), ('2026-11-02', 'Finados'), ('2026-11-15', 'Proclamação da República'),
  ('2026-11-20', 'Consciência Negra'), ('2026-12-25', 'Natal'), ('2027-01-01', 'Confraternização');

insert into senhor_smart_at.categorias (id, nome, atende, fila_transferencia) values
  ('celular', 'Celular', true, 'tecnico'),
  ('tablet', 'Tablet', true, 'tecnico'),
  ('notebook', 'Notebook', true, 'tecnico'),
  ('videogame', 'Videogame', true, 'tecnico'),
  ('computador', 'Computador de mesa', true, 'tecnico'),
  ('smartwatch', 'Smartwatch', true, 'tecnico'),
  ('tv', 'Televisão', false, null),
  ('eletrodomestico', 'Eletrodoméstico', false, null);

-- Modelos → linha de preço. Padrões específicos (prioridade baixa) antes dos genéricos.
insert into senhor_smart_at.modelos (categoria, marca, padrao, exibicao, linha, prioridade) values
  -- Apple
  ('celular', 'Apple', 'iphone\s*(1[4-7])', 'iPhone \1', 'apple_recente', 10),
  ('celular', 'Apple', 'iphone\s*(1[23])', 'iPhone \1', 'apple_medio', 10),
  ('celular', 'Apple', 'iphone\s*(se|[6-9]|x[rs]?|11)\M', 'iPhone \1', 'apple_antigo', 10),
  ('celular', 'Apple', 'iphone', 'iPhone', 'apple_medio', 90),
  ('tablet', 'Apple', 'ipad', 'iPad', 'premium', 20),
  ('notebook', 'Apple', 'mac\s*book', 'MacBook', 'premium', 20),
  ('smartwatch', 'Apple', 'apple\s*watch', 'Apple Watch', 'premium', 20),
  -- Samsung
  ('celular', 'Samsung', '\m(s2[0-6]|s1[0-9]|note\s*[0-9]+|z\s*(flip|fold))', 'Galaxy \1', 'premium', 20),
  ('celular', 'Samsung', '\ma\s*([0-1][0-9])\M', 'Galaxy A\1', 'entrada', 30),
  ('celular', 'Samsung', '\ma\s*([2-9][0-9])\s*s?\M', 'Galaxy A\1', 'intermediario', 30),
  ('celular', 'Samsung', '\mm\s*([0-9]{2})\M', 'Galaxy M\1', 'entrada', 40),
  ('celular', 'Samsung', 'samsung|galaxy', 'Samsung', 'intermediario', 90),
  ('tablet', 'Samsung', 'galaxy\s*tab|tab\s*[as]', 'Galaxy Tab', 'intermediario', 20),
  -- Motorola
  ('celular', 'Motorola', 'edge', 'Motorola Edge', 'premium', 20),
  ('celular', 'Motorola', '\mg\s*([5-9][0-9])\M', 'Moto G\1', 'intermediario', 30),
  ('celular', 'Motorola', '\mg\s*([0-4][0-9]|[0-9])\M', 'Moto G\1', 'entrada', 30),
  ('celular', 'Motorola', '\mmoto\s*e\s*([0-9]+)', 'Moto E\1', 'entrada', 30),
  ('celular', 'Motorola', 'motorola|\mmoto\M', 'Motorola', 'entrada', 90),
  -- Xiaomi
  ('celular', 'Xiaomi', 'redmi\s*note', 'Redmi Note', 'intermediario', 20),
  ('celular', 'Xiaomi', '\mpoco\M', 'Poco', 'intermediario', 20),
  ('celular', 'Xiaomi', 'redmi', 'Redmi', 'entrada', 30),
  ('celular', 'Xiaomi', 'xiaomi|\mmi\s*[0-9]', 'Xiaomi', 'intermediario', 90),
  -- Outros celulares
  ('celular', 'Realme', 'realme', 'Realme', 'entrada', 50),
  ('celular', 'LG', '\mlg\M', 'LG', 'entrada', 50),
  ('celular', 'Asus', 'zenfone', 'Zenfone', 'intermediario', 50),
  -- Videogames
  ('videogame', 'Sony', 'ps\s*5|playstation\s*5', 'PlayStation 5', 'premium', 10),
  ('videogame', 'Sony', 'ps\s*4|playstation\s*4', 'PlayStation 4', 'intermediario', 10),
  ('videogame', 'Sony', 'dual\s*sense|controle.*ps\s*5', 'Controle DualSense', 'padrao', 5),
  ('videogame', 'Sony', 'dual\s*shock|controle.*ps\s*4', 'Controle DualShock 4', 'padrao', 5),
  ('videogame', 'Microsoft', 'xbox\s*series|series\s*[xs]', 'Xbox Series', 'premium', 10),
  ('videogame', 'Microsoft', 'xbox\s*one', 'Xbox One', 'intermediario', 10),
  ('videogame', 'Microsoft', 'xbox', 'Xbox', 'intermediario', 80),
  ('videogame', 'Nintendo', 'switch|joy\s*-?\s*con', 'Nintendo Switch', 'intermediario', 10),
  -- Notebooks
  ('notebook', 'Dell', 'dell|inspiron|vostro|latitude', 'Dell', 'padrao', 40),
  ('notebook', 'Lenovo', 'lenovo|ideapad|thinkpad', 'Lenovo', 'padrao', 40),
  ('notebook', 'Acer', 'acer|aspire|nitro', 'Acer', 'padrao', 40),
  ('notebook', 'Samsung', 'samsung\s*book|galaxy\s*book', 'Samsung Book', 'padrao', 40),
  ('notebook', 'Asus', 'asus|vivobook|tuf', 'Asus', 'padrao', 40),
  ('notebook', 'HP', '\mhp\M|pavilion|elitebook', 'HP', 'padrao', 40),
  ('notebook', 'Positivo', 'positivo|vaio', 'Positivo/Vaio', 'padrao', 40);

insert into senhor_smart_at.servicos (id, categoria, nome, sintomas, prazo_texto, exige_diagnostico, observacao) values
  ('cel_tela', 'celular', 'Troca de tela', '{tela,display,trincou,quebrou,riscos,listras,mancha,"não acende","tela preta","touch",toque}', 'mesmo dia, se houver peça em estoque', false, 'Tela que não acende após queda pode ser display ou placa: confirmado na avaliação.'),
  ('cel_bateria', 'celular', 'Troca de bateria', '{bateria,descarrega,"não segura carga",estufada,inchada,desliga sozinho}', 'cerca de 1 hora', false, null),
  ('cel_conector', 'celular', 'Troca do conector de carga', '{"não carrega",carregador,conector,"entrada do carregador","mau contato"}', 'cerca de 1 hora', false, 'Às vezes é só sujeira no conector: limpeza resolve.'),
  ('cel_camera', 'celular', 'Reparo de câmera', '{câmera,camera,foto,embaçada,"não foca"}', 'mesmo dia', false, null),
  ('cel_vidro_traseiro', 'celular', 'Troca da tampa traseira', '{tampa,traseira,"vidro de trás","parte de trás"}', 'mesmo dia', false, null),
  ('cel_audio', 'celular', 'Reparo de alto-falante ou microfone', '{som,"alto-falante",microfone,"não ouço","não me escutam"}', 'mesmo dia', false, null),
  ('cel_agua', 'celular', 'Limpeza química (contato com água)', '{água,agua,molhou,caiu na água,oxidação,oxidado,piscina,molhado,chuva,vaso,mar,umidade}', '24 a 72h', true, 'Desligar o aparelho e não carregar até a avaliação.'),
  ('cel_placa', 'celular', 'Reparo de placa', '{"não liga","não dá sinal",reiniciando,"travado no logo",placa,esquentando}', 'avaliação em até 48h', true, null),
  ('cel_software', 'celular', 'Formatação e atualização', '{lento,travando,formatar,vírus,atualizar,sistema}', 'cerca de 2 horas', false, 'Backup dos dados antes, quando possível.'),
  ('tab_tela', 'tablet', 'Troca de tela de tablet', '{tela,display,trincou,quebrou,touch}', '1 a 3 dias', false, null),
  ('tab_bateria', 'tablet', 'Troca de bateria de tablet', '{bateria,descarrega,estufada}', '1 a 2 dias', false, null),
  ('nb_tela', 'notebook', 'Troca de tela de notebook', '{tela,display,quebrou,trincou,listras,"tela preta",mancha}', '1 a 3 dias', false, null),
  ('nb_teclado', 'notebook', 'Troca de teclado', '{teclado,tecla,teclas}', '1 a 3 dias', false, null),
  ('nb_bateria', 'notebook', 'Troca de bateria de notebook', '{bateria,"só funciona na tomada",descarrega}', '1 a 3 dias', false, null),
  ('nb_limpeza', 'notebook', 'Limpeza interna e pasta térmica', '{esquentando,quente,barulho,ventoinha,cooler,desligando}', 'mesmo dia', false, null),
  ('nb_ssd', 'notebook', 'Upgrade para SSD (com peça)', '{lento,demora,ssd,"ligar rápido",hd}', 'mesmo dia', false, 'Inclui SSD de 240GB a 480GB e clonagem do sistema.'),
  ('nb_formatacao', 'notebook', 'Formatação com backup', '{formatar,vírus,windows,sistema,lento}', '1 dia', false, null),
  ('nb_conector', 'notebook', 'Troca do conector de energia', '{"não carrega",carregador,conector,"mau contato"}', '1 a 2 dias', false, null),
  ('nb_placa', 'notebook', 'Reparo de placa de notebook', '{"não liga","sem imagem",placa,água,molhou}', 'avaliação em até 72h', true, null),
  ('vg_limpeza', 'videogame', 'Limpeza e troca de pasta térmica', '{barulho,esquentando,quente,ventoinha,desligando}', 'mesmo dia', false, null),
  ('vg_hdmi', 'videogame', 'Troca da porta HDMI', '{hdmi,"sem imagem","não dá vídeo","sem sinal"}', '1 a 2 dias', false, null),
  ('vg_controle', 'videogame', 'Reparo de controle (analógico/drift)', '{controle,analógico,analogico,drift,"anda sozinho",botão}', 'mesmo dia', false, null),
  ('vg_leitor', 'videogame', 'Reparo do leitor de disco', '{disco,leitor,"não lê","não puxa"}', 'avaliação em até 72h', true, null),
  ('vg_placa', 'videogame', 'Reparo de placa de console', '{"não liga","luz azul","luz vermelha",placa}', 'avaliação em até 72h', true, null),
  ('sw_reparo', 'smartwatch', 'Reparo de smartwatch', '{tela,bateria,"não liga",pulseira}', 'avaliação na loja', true, null),
  ('pc_manutencao', 'computador', 'Manutenção de computador', '{lento,"não liga",formatar,limpeza}', 'avaliação na loja', true, null);

-- Faixas de referência (R$). Fonte: estimativa de mercado de assistência independente.
insert into senhor_smart_at.preco_referencia (servico_id, linha, preco_min, preco_max) values
  ('cel_tela', 'entrada', 180, 350), ('cel_tela', 'intermediario', 280, 650), ('cel_tela', 'premium', 700, 1600),
  ('cel_tela', 'apple_antigo', 350, 800), ('cel_tela', 'apple_medio', 600, 1300), ('cel_tela', 'apple_recente', 1000, 2400),
  ('cel_bateria', 'entrada', 120, 200), ('cel_bateria', 'intermediario', 150, 280), ('cel_bateria', 'premium', 250, 450),
  ('cel_bateria', 'apple_antigo', 200, 380), ('cel_bateria', 'apple_medio', 280, 480), ('cel_bateria', 'apple_recente', 380, 700),
  ('cel_conector', 'entrada', 90, 180), ('cel_conector', 'intermediario', 120, 250), ('cel_conector', 'premium', 200, 400),
  ('cel_conector', 'apple_antigo', 200, 350), ('cel_conector', 'apple_medio', 250, 450), ('cel_conector', 'apple_recente', 300, 550),
  ('cel_camera', 'entrada', 120, 250), ('cel_camera', 'intermediario', 180, 400), ('cel_camera', 'premium', 300, 800),
  ('cel_camera', 'apple_antigo', 300, 600), ('cel_camera', 'apple_medio', 400, 800), ('cel_camera', 'apple_recente', 500, 1100),
  ('cel_vidro_traseiro', null, 120, 450),
  ('cel_audio', null, 90, 250),
  ('cel_software', null, 60, 120),
  ('tab_tela', null, 300, 900), ('tab_tela', 'premium', 700, 1800),
  ('tab_bateria', null, 200, 400),
  ('nb_tela', 'padrao', 350, 900), ('nb_tela', 'premium', 1500, 4000),
  ('nb_teclado', 'padrao', 180, 450), ('nb_teclado', 'premium', 600, 1500),
  ('nb_bateria', 'padrao', 250, 600), ('nb_bateria', 'premium', 700, 1500),
  ('nb_limpeza', null, 120, 250),
  ('nb_ssd', null, 250, 600),
  ('nb_formatacao', null, 100, 200),
  ('nb_conector', null, 150, 300),
  ('vg_limpeza', null, 150, 300),
  ('vg_hdmi', null, 250, 500),
  ('vg_controle', null, 100, 200);

-- Origem: as campanhas devem usar mensagens pré-preenchidas distintas (como a TX faz com "Google ADS Samsung").
insert into senhor_smart_at.origem_regra (prioridade, campo, padrao, canal, campanha) values
  (10, 'anuncio', '%', 'meta', 'Anúncio Meta (click-to-WhatsApp)'),
  (20, 'mensagem', '%vim pelo google%', 'google', 'Google Ads'),
  (20, 'mensagem', '%encontrei no google%', 'google', 'Google Ads'),
  (20, 'mensagem', '%vi no google%', 'google', 'Google Ads'),
  (30, 'mensagem', '%vi o an_ncio%', 'meta', 'Anúncio Meta'),
  (30, 'mensagem', '%instagram%', 'meta', 'Instagram'),
  (40, 'mensagem', '%site%', 'site', 'Site'),
  (50, 'mensagem', '%indica%', 'indicacao', 'Indicação');

-- Biblioteca de estratégias (primeira que casa, por prioridade)
insert into senhor_smart_at.conversation_strategies
  (nome, prioridade, quando_intent, quando_sentimento, quando_etapa, quando_primeira, quando_tem_categoria, quando_tem_modelo, quando_tem_defeito, quando_tem_preco, quando_categoria_atendida,
   objetivo, acolher_antes, pode_cotar, proximo_passo, transferir_fila) values
  ('pediu_humano',        10, '{pediu_humano}', null, null, null, null, null, null, null, null, 'encaminhar', false, false, null, 'humano'),
  ('reclamacao_status',   20, '{reclamacao,status_servico,garantia}', null, null, null, null, null, null, null, null, 'acolher_e_encaminhar', true, false, null, 'humano'),
  ('compra_aparelho',     30, '{comprar_aparelho}', null, null, null, null, null, null, null, null, 'encaminhar_vendas', false, false, null, 'vendas'),
  ('despedida',           40, '{despedida}', null, null, null, null, null, null, null, null, 'encerrar', false, false, null, null),
  ('categoria_nao_atendida', 50, null, null, null, null, true, null, null, null, false, 'informar_nao_atende', false, false, null, null),
  ('confirmou_visita',    60, '{confirmar_visita}', null, null, null, null, null, null, null, null, 'confirmar_visita', false, false, 'confirmar_dia', 'tecnico'),
  ('local_horario',       70, '{endereco,horario}', null, null, null, null, null, null, null, null, 'informar_local', false, true, 'proximo_dado', null),
  ('objecao_preco',       80, '{objecao_preco}', null, null, null, null, null, null, null, null, 'tratar_objecao', true, true, 'convidar_avaliacao', null),
  ('abertura_cumprimento', 90, '{saudacao}', null, null, true, false, null, null, null, null, 'recepcionar', false, false, 'perguntar_equipamento', null),
  ('inseguro',           100, null, '{ansioso,frustrado,preocupado}', '{novo,triagem,diagnostico}', null, null, null, null, null, null, 'acolher', true, false, 'proximo_dado', null),
  ('falta_equipamento',  110, null, null, null, null, false, null, null, null, null, 'descobrir_equipamento', false, false, 'perguntar_equipamento', null),
  ('falta_defeito',      120, null, null, null, null, true, null, false, null, null, 'diagnosticar', false, false, 'perguntar_defeito', null),
  ('falta_modelo',       130, null, null, null, null, true, false, true, null, null, 'identificar_modelo', false, false, 'perguntar_modelo', null),
  ('cotar',              140, null, null, '{triagem,diagnostico}', null, true, true, true, true, true, 'cotar', false, true, 'convidar_avaliacao', null),
  ('precisa_avaliacao',  150, null, null, '{triagem,diagnostico}', null, true, true, true, false, true, 'convidar_avaliacao', false, false, 'convidar_avaliacao', null),
  ('pos_orcamento',      160, null, null, '{orcamento}', null, null, null, null, null, null, 'conduzir_visita', false, true, 'detalhe_pratico', null),
  ('padrao',             999, null, null, null, null, null, null, null, null, null, 'responder', false, true, 'proximo_dado', null);
