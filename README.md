# ASCII Christmas Tree

Uma árvore de Natal 3D feita com caracteres ASCII, renderizada em uma janela
gráfica usando Python, Pygame e NumPy.

Durante a animação, a árvore cresce, gira, recebe enfeites e termina com uma
mensagem de Feliz Natal:

```text
                         *
                        /\
                       /  \
                      / .  \
                     /  *   \
                    / .  o   \
                   / *   .    \
                  /____________\
                       ||||
                    __ |||| __
                   |__|____|__|

                 FELIZ NATAL 2026!!
```

## Funcionalidades

- Árvore formada por pontos e caracteres ASCII coloridos.
- Rotação contínua em 3D.
- Animação de crescimento da base até o topo.
- Garlandas, bolas, luzes, estrela e presentes.
- Fundo com estrelas.
- Mensagem animada `FELIZ NATAL 2026!!`.
- Salvamento de screenshots em PNG.

## Requisitos

- Python 3.9 ou superior
- [Pygame](https://www.pygame.org/)
- [NumPy](https://numpy.org/)

## Instalação

No terminal, dentro desta pasta, execute:

```bash
python -m pip install pygame numpy
```

## Como executar

```bash
python christmas_tree.py
```

No Linux ou macOS, também é possível usar:

```bash
python3 christmas_tree.py
```

## Controles

| Tecla | Ação |
|---|---|
| `Espaço` | Pausar ou continuar a animação |
| `R` | Reiniciar o crescimento da árvore |
| `S` | Salvar uma screenshot em PNG |
| `Esc` | Fechar o programa |

## Como funciona

O programa cria uma nuvem de pontos tridimensional para representar a árvore.
Esses pontos são projetados em uma grade de caracteres, recebem cores e são
desenhados em uma janela do Pygame a 30 quadros por segundo.

A sequência visual da animação é:

1. Crescimento dos galhos.
2. Aparição do tronco.
3. Garlandas e bolas.
4. Luzes piscando.
5. Estrela no topo.
6. Mensagem de Natal.

## Estrutura

```text
merry christmas/
├── christmas_tree.py
└── README.md
```

## Licença

Projeto criado para fins de estudo e diversão.
