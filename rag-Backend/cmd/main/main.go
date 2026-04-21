package main

import (
	"github.com/gin-gonic/gin"
	"github.com/keshav/bookstore/package/models"
	"github.com/keshav/bookstore/package/routes"
)

func main() {
	r := gin.Default()

	models.Init()

	routes.RegisterBookRoutes(r)

	r.Run("localhost:8000")
}
