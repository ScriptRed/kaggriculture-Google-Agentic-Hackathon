.PHONY: arena quick test freeze submit clean

arena:
	python arena/run.py --json arena/results/latest.json

quick:
	python arena/run.py --quick

test:
	python -m pytest tests/ -q

freeze:
	@test -n "$(NAME)" || (echo "usage: make freeze NAME=v1-somename"; exit 1)
	mkdir -p arena/opponents/$(NAME)
	cp agent/*.py arena/opponents/$(NAME)/
	@echo "frozen as arena/opponents/$(NAME) - add it to DEFAULT_OPPONENTS"

submit:
	@test -n "$(MSG)" || (echo 'usage: make submit MSG="what changed"'; exit 1)
	cd agent && tar -czf ../submission.tar.gz main.py constants.py policy/
	kaggle competitions submit kaggriculture -f submission.tar.gz -m "$(MSG)"

clean:
	rm -rf **/__pycache__ submission.tar.gz arena/results/*.json
